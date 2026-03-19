"""Unit tests for the SQLite store and enrichment ingest hook."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.exceptions import SearchValidationError  # noqa: E402
from core.repl.search_command_parser import parse_sqlite_search_command  # noqa: E402
from core.store.connection import ConnectionFactory  # noqa: E402
from core.store.repositories.findings import (  # noqa: E402
    FindingRepository,
    _normalise_cwe,
    _normalise_finding_type,
)
from core.store.repositories.runs import RunRepository  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(
    tmp_path: Path,
) -> tuple[ConnectionFactory, RunRepository, FindingRepository]:
    factory = ConnectionFactory(
        tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    )
    factory.init_schema()
    return factory, RunRepository(factory), FindingRepository(factory)


def _seed_two_tools(run_repo: RunRepository, finding_repo: FindingRepository) -> None:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(
        run_id,
        [
            {
                "tool": "semgrep",
                "severity": "high",
                "file_path": "foo.py",
                "rule_id": "r1",
            },
            {
                "tool": "gitleaks",
                "severity": "critical",
                "file_path": "bar.py",
                "rule_id": "g1",
                "line_number": 1,
            },
        ],
    )


# ---------------------------------------------------------------------------
# Validated flags — rejection / acceptance
# ---------------------------------------------------------------------------


class TestValidatedFlags:
    _known: frozenset[str] = frozenset({"gitleaks", "semgrep", "nmap"})

    def test_invalid_tool_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="not found"):
            parse_sqlite_search_command(["--tool=badtool"], self._known)

    def test_valid_tool_passes(self) -> None:
        result = parse_sqlite_search_command(["--tool=gitleaks"], self._known)
        conds = result["conditions"]
        assert len(conds) == 1
        col, op, vals = conds[0]
        assert col == "tool"
        assert op == "="
        assert vals == ["gitleaks"]

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="severity"):
            parse_sqlite_search_command(["--severity=extreme"], self._known)

    def test_valid_severity_passes(self) -> None:
        result = parse_sqlite_search_command(["--severity=high"], self._known)
        col, op, vals = result["conditions"][0]
        assert col == "severity" and op == "=" and vals == ["high"]

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="type"):
            parse_sqlite_search_command(["--type=bogus"], self._known)

    def test_invalid_domain_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="domain"):
            parse_sqlite_search_command(["--domain=space"], self._known)

    def test_contains_bypasses_validation(self) -> None:
        result = parse_sqlite_search_command(["--severity~=crit"], self._known)
        assert result["conditions"][0][1] == "~="

    def test_tool_contains_bypasses_validation(self) -> None:
        result = parse_sqlite_search_command(["--tool~=leak"], self._known)
        col, op, vals = result["conditions"][0]
        assert op == "~=" and vals == ["leak"]

    def test_meta_flag_resolves_to_json_extract(self) -> None:
        result = parse_sqlite_search_command(["--risk_type=sql_injection"], self._known)
        col, op, vals = result["conditions"][0]
        assert "json_extract" in col
        assert "risk_type" in col

    def test_alert_maps_to_alert_name(self) -> None:
        result = parse_sqlite_search_command(["--alert=sqli"], self._known)
        col, _, _ = result["conditions"][0]
        assert "alert_name" in col

    def test_unknown_flag_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="Unknown filter flag"):
            parse_sqlite_search_command(["--nonexistent=foo"], self._known)

    def test_csv_tool_produces_in_list(self) -> None:
        result = parse_sqlite_search_command(["--tool=gitleaks,semgrep"], self._known)
        col, op, vals = result["conditions"][0]
        assert op == "=" and vals == ["gitleaks", "semgrep"]

    def test_pagination_flags(self) -> None:
        result = parse_sqlite_search_command(
            ["--page=3", "--page-size=10"], self._known
        )
        assert result["page"] == 3
        assert result["page_size"] == 10

    def test_bad_page_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="--page"):
            parse_sqlite_search_command(["--page=0"], self._known)

    def test_bad_page_size_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="--page-size"):
            parse_sqlite_search_command(["--page-size=-1"], self._known)


# ---------------------------------------------------------------------------
# Run management helpers
# ---------------------------------------------------------------------------


class TestRunManagement:
    def test_create_run_returns_int(self, tmp_path: Path) -> None:
        _, run_repo, _ = _make_store(tmp_path)
        run_id = run_repo.create_run({"tool": "gitleaks"})
        assert isinstance(run_id, int)
        assert run_id >= 1

    def test_add_run_tools_inserts_row_per_tool(self, tmp_path: Path) -> None:
        factory, run_repo, _ = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        run_repo.add_run_tools(
            run_id,
            [
                {"tool": "gitleaks", "findings_count": 3},
                {"tool": "semgrep", "findings_count": 1},
            ],
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT tool FROM run_tools WHERE run_id=?", (run_id,)
            ).fetchall()
        tools = [r[0] for r in rows]
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert len(tools) == 2

    def test_add_run_repos_inserts_row_per_repo(self, tmp_path: Path) -> None:
        factory, run_repo, _ = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        run_repo.add_run_repos(run_id, ["repo-a", "repo-b", "repo-c"])
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT repo FROM run_repos WHERE run_id=?", (run_id,)
            ).fetchall()
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# delete_findings
# ---------------------------------------------------------------------------


class TestDeleteFindings:
    def test_delete_none_clears_all_tables(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo = _make_store(tmp_path)
        _seed_two_tools(run_repo, finding_repo)

        finding_repo.delete_findings(tools=None)

        with factory.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM run_tools").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM run_repos").fetchone()[0] == 0

    def test_delete_by_tool_removes_only_that_tool(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo = _make_store(tmp_path)
        _seed_two_tools(run_repo, finding_repo)

        finding_repo.delete_findings(tools=["semgrep"])

        with factory.connect() as conn:
            rows = conn.execute("SELECT tool FROM findings").fetchall()
        tools = [r[0] for r in rows]
        assert "semgrep" not in tools
        assert "gitleaks" in tools

    def test_delete_by_tool_keeps_runs(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo = _make_store(tmp_path)
        _seed_two_tools(run_repo, finding_repo)

        finding_repo.delete_findings(tools=["semgrep"])

        with factory.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] >= 1


# ---------------------------------------------------------------------------
# Enrichment ingest hook
# ---------------------------------------------------------------------------


class TestIngestHook:
    def test_hook_fires_after_enrich(self) -> None:
        """upsert_findings is called after enrich() completes."""
        from core.rag.enrichment import EnrichmentPipeline

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "test finding text",
            "metadata": {"tool": "gitleaks", "severity": "high"},
        }
        mock_repo = MagicMock()
        pipeline = EnrichmentPipeline(
            mock_engine,
            finding_repo=mock_repo,
            run_id=42,
            llm_provider=MagicMock(),
        )
        # Bypass actual LLM call
        pipeline._call_llm_worker = MagicMock(return_value={})  # type: ignore[method-assign]

        pipeline.enrich(["doc1"])

        mock_repo.upsert_findings.assert_called_once_with(
            42, [{"tool": "gitleaks", "severity": "high"}]
        )

    def test_hook_fires_with_multiple_docs(self) -> None:
        from core.rag.enrichment import EnrichmentPipeline

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.side_effect = lambda doc_id: {
            "id": doc_id,
            "document": "text",
            "metadata": {"tool": "semgrep", "rule_id": doc_id},
        }
        mock_repo = MagicMock()
        pipeline = EnrichmentPipeline(
            mock_engine,
            finding_repo=mock_repo,
            run_id=7,
            llm_provider=MagicMock(),
        )
        pipeline._call_llm_worker = MagicMock(return_value={})  # type: ignore[method-assign]

        pipeline.enrich(["d1", "d2", "d3"])

        call_args = mock_repo.upsert_findings.call_args
        assert call_args[0][0] == 7  # run_id
        findings = call_args[0][1]
        assert len(findings) == 3

    def test_hook_not_called_when_no_repo(self) -> None:
        from core.rag.enrichment import EnrichmentPipeline

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "text",
            "metadata": {"tool": "nmap"},
        }
        pipeline = EnrichmentPipeline(mock_engine)

        # Should not raise even without repo; nmap provides all fields so no LLM call
        pipeline.enrich(["doc1"])

    def test_hook_failure_does_not_raise(self) -> None:
        """SQLite failure in the hook must not interrupt the scan."""
        from core.rag.enrichment import EnrichmentPipeline

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "text",
            "metadata": {"tool": "gitleaks"},
        }
        mock_repo = MagicMock()
        mock_repo.upsert_findings.side_effect = RuntimeError("DB locked")
        pipeline = EnrichmentPipeline(
            mock_engine,
            finding_repo=mock_repo,
            run_id=1,
            llm_provider=MagicMock(),
        )
        pipeline._call_llm_worker = MagicMock(return_value={})  # type: ignore[method-assign]

        # Must not raise
        pipeline.enrich(["doc1"])


# ---------------------------------------------------------------------------
# _normalise_finding_type unit tests
# ---------------------------------------------------------------------------


class TestFindingTypeNormalisation:
    def test_plain_string_secret(self) -> None:
        assert _normalise_finding_type("secret") == '["secret"]'

    def test_already_array_is_idempotent(self) -> None:
        assert _normalise_finding_type('["secret"]') == '["secret"]'

    def test_invalid_value_returns_none(self) -> None:
        result = _normalise_finding_type("bogus")
        assert result is None

    def test_mixed_valid_and_invalid(self) -> None:
        import json

        result = _normalise_finding_type('["secret", "bogus"]')
        assert result is not None
        items = json.loads(result)
        assert items == ["secret"]
        assert "bogus" not in items


# ---------------------------------------------------------------------------
# _normalise_cwe unit tests
# ---------------------------------------------------------------------------


class TestCweNormalisationUnit:
    def test_none_returns_none(self) -> None:
        assert _normalise_cwe(None) is None

    def test_int_produces_cwe_prefix(self) -> None:
        import json

        result = _normalise_cwe(89)
        assert result is not None
        assert json.loads(result) == ["CWE-89"]

    def test_plain_string(self) -> None:
        import json

        result = _normalise_cwe("CWE-89")
        assert result is not None
        assert json.loads(result) == ["CWE-89"]

    def test_list_input(self) -> None:
        import json

        result = _normalise_cwe(["CWE-89", "CWE-20"])
        assert result is not None
        items = json.loads(result)
        assert "CWE-89" in items
        assert "CWE-20" in items

    def test_comma_joined_string(self) -> None:
        import json

        result = _normalise_cwe("CWE-89, CWE-20")
        assert result is not None
        items = json.loads(result)
        assert "CWE-89" in items
        assert "CWE-20" in items


# ---------------------------------------------------------------------------
# finding_type json_each filter (real SQLite)
# ---------------------------------------------------------------------------


class TestFindingTypeJsonEach:
    def test_exact_match_secret_does_not_return_vulnerability(
        self, tmp_path: Path
    ) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["finding_type"] == ["secret"] for r in results)
        assert not any(r["metadata"].get("tool") == "semgrep" for r in results)

    def test_exact_match_multi_value_returns_both_types(self, tmp_path: Path) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "=", ["secret", "vulnerability"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert "nmap" not in tools

    def test_partial_match_vuln_matches_vulnerability(self, tmp_path: Path) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "~=", ["vuln"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all(r["metadata"]["tool"] == "semgrep" for r in results)

    def test_exact_match_does_not_return_unrelated_type(self, tmp_path: Path) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert results == []


# ---------------------------------------------------------------------------
# triage_batches schema
# ---------------------------------------------------------------------------


class TestTriageBatchesSchema:
    def test_table_exists(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        with factory.connect() as conn:
            sql = (
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND name='triage_batches'"
            )
            row = conn.execute(sql).fetchone()
        assert row is not None

    def test_all_columns_exist(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        with factory.connect() as conn:
            rows = conn.execute("PRAGMA table_info(triage_batches)").fetchall()
        col_names = {r[1] for r in rows}
        expected = {
            "id",
            "run_id",
            "finding_ids",
            "batch_data",
            "status",
            "run_attempts",
            "created_at",
            "started_at",
            "completed_at",
        }
        assert expected == col_names

    def _insert_minimal(self, factory: ConnectionFactory) -> int:
        with factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO triage_batches (finding_ids, batch_data) VALUES (?, ?)",
                ("[1,2]", "[]"),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def test_status_defaults_to_pending(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE id=?", (row_id,)
            ).fetchone()
        assert row[0] == "pending"

    def test_run_attempts_defaults_to_zero(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT run_attempts FROM triage_batches WHERE id=?", (row_id,)
            ).fetchone()
        assert row[0] == 0

    def test_created_at_auto_populated(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM triage_batches WHERE id=?", (row_id,)
            ).fetchone()
        assert row[0] is not None

    def test_started_at_and_completed_at_nullable(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT started_at, completed_at FROM triage_batches WHERE id=?",
                (row_id,),
            ).fetchone()
        assert row[0] is None
        assert row[1] is None

"""Unit tests for the SQLite store and enrichment ingest hook."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.store.sqlite_store import (  # noqa: E402
    SearchValidationError,
    SQLiteStore,
    parse_sqlite_search_command,
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
        """~= on a validated flag should not raise for out-of-vocabulary values."""
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
        store = SQLiteStore(tmp_path, "proj")
        store._init_schema()
        run_id = store.create_run({"tool": "gitleaks"})
        assert isinstance(run_id, int)
        assert run_id >= 1

    def test_add_run_tools_inserts_row_per_tool(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path, "proj")
        store._init_schema()
        run_id = store.create_run({})
        store.add_run_tools(
            run_id,
            [
                {"tool": "gitleaks", "findings_count": 3},
                {"tool": "semgrep", "findings_count": 1},
            ],
        )
        conn = store._connect()
        rows = conn.execute(
            "SELECT tool FROM run_tools WHERE run_id=?", (run_id,)
        ).fetchall()
        tools = [r[0] for r in rows]
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert len(tools) == 2

    def test_add_run_repos_inserts_row_per_repo(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path, "proj")
        store._init_schema()
        run_id = store.create_run({})
        store.add_run_repos(run_id, ["repo-a", "repo-b", "repo-c"])
        conn = store._connect()
        rows = conn.execute(
            "SELECT repo FROM run_repos WHERE run_id=?", (run_id,)
        ).fetchall()
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# delete_findings
# ---------------------------------------------------------------------------


def _seed_two_tools(store: SQLiteStore) -> None:
    run_id = store.create_run({})
    store.upsert_findings(
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


class TestDeleteFindings:
    def test_delete_none_clears_all_tables(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path, "proj")
        store._init_schema()
        _seed_two_tools(store)

        store.delete_findings(tools=None)

        conn = store._connect()
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM run_tools").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM run_repos").fetchone()[0] == 0

    def test_delete_by_tool_removes_only_that_tool(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path, "proj")
        store._init_schema()
        _seed_two_tools(store)

        store.delete_findings(tools=["semgrep"])

        conn = store._connect()
        rows = conn.execute("SELECT tool FROM findings").fetchall()
        tools = [r[0] for r in rows]
        assert "semgrep" not in tools
        assert "gitleaks" in tools

    def test_delete_by_tool_keeps_runs(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path, "proj")
        store._init_schema()
        _seed_two_tools(store)

        store.delete_findings(tools=["semgrep"])

        conn = store._connect()
        # run rows must remain (not deleted for tool-specific purge)
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
        mock_store = MagicMock()
        pipeline = EnrichmentPipeline(mock_engine, sqlite_store=mock_store, run_id=42)
        # Bypass actual LLM call
        pipeline._enrich_one = MagicMock(return_value=1)

        pipeline.enrich(["doc1"])

        mock_store.upsert_findings.assert_called_once_with(
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
        mock_store = MagicMock()
        pipeline = EnrichmentPipeline(mock_engine, sqlite_store=mock_store, run_id=7)
        pipeline._enrich_one = MagicMock(return_value=1)

        pipeline.enrich(["d1", "d2", "d3"])

        call_args = mock_store.upsert_findings.call_args
        assert call_args[0][0] == 7  # run_id
        findings = call_args[0][1]
        assert len(findings) == 3

    def test_hook_not_called_when_no_store(self) -> None:
        from core.rag.enrichment import EnrichmentPipeline

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "text",
            "metadata": {"tool": "nmap"},
        }
        pipeline = EnrichmentPipeline(mock_engine)
        pipeline._enrich_one = MagicMock(return_value=1)

        # Should not raise even without store
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
        mock_store = MagicMock()
        mock_store.upsert_findings.side_effect = RuntimeError("DB locked")
        pipeline = EnrichmentPipeline(mock_engine, sqlite_store=mock_store, run_id=1)
        pipeline._enrich_one = MagicMock(return_value=1)

        # Must not raise
        pipeline.enrich(["doc1"])

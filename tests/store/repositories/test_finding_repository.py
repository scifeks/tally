"""Tests for FindingRepository, including normalization helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.store.connection import ConnectionFactory  # noqa: E402
from core.store.repositories.findings import FindingRepository  # noqa: E402
from core.store.repositories.findings_serial import (  # noqa: E402
    normalise_cwe,
    normalise_finding_type,
)
from core.store.repositories.runs import RunRepository  # noqa: E402


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
) -> int:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, findings)
    return run_id


# ---------------------------------------------------------------------------
# _normalise_finding_type
# ---------------------------------------------------------------------------


class TestFindingTypeNormalisation:
    def test_plain_string_secret(self) -> None:
        assert normalise_finding_type("secret") == '["secret"]'

    def test_already_array_is_idempotent(self) -> None:
        assert normalise_finding_type('["secret"]') == '["secret"]'

    def test_invalid_value_returns_none(self) -> None:
        result = normalise_finding_type("bogus")
        assert result is None

    def test_mixed_valid_and_invalid(self) -> None:
        result = normalise_finding_type('["secret", "bogus"]')
        assert result is not None
        items = json.loads(result)
        assert items == ["secret"]
        assert "bogus" not in items


# ---------------------------------------------------------------------------
# _normalise_cwe
# ---------------------------------------------------------------------------


class TestCweNormalisationUnit:
    def test_none_returns_none(self) -> None:
        assert normalise_cwe(None) is None

    def test_int_produces_cwe_prefix(self) -> None:
        result = normalise_cwe(89)
        assert result is not None
        assert json.loads(result) == ["CWE-89"]

    def test_plain_string(self) -> None:
        result = normalise_cwe("CWE-89")
        assert result is not None
        assert json.loads(result) == ["CWE-89"]

    def test_list_input(self) -> None:
        result = normalise_cwe(["CWE-89", "CWE-20"])
        assert result is not None
        items = json.loads(result)
        assert "CWE-89" in items
        assert "CWE-20" in items

    def test_comma_joined_string(self) -> None:
        result = normalise_cwe("CWE-89, CWE-20")
        assert result is not None
        items = json.loads(result)
        assert "CWE-89" in items
        assert "CWE-20" in items


# ---------------------------------------------------------------------------
# upsert_findings / delete_findings
# ---------------------------------------------------------------------------


class TestUpsertAndDelete:
    def test_upsert_inserts_row(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "gitleaks", "severity": "high"}])
        with factory.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 1

    def test_delete_none_clears_all_tables(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {"tool": "semgrep", "severity": "high", "file_path": "foo.py"},
                {"tool": "gitleaks", "severity": "critical", "file_path": "bar.py"},
            ],
        )
        repo.delete_findings(tools=None)
        with factory.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM run_tools").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM run_repos").fetchone()[0] == 0

    def test_delete_by_tool_removes_only_that_tool(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {"tool": "semgrep", "severity": "high", "file_path": "foo.py"},
                {"tool": "gitleaks", "severity": "critical", "file_path": "bar.py"},
            ],
        )
        repo.delete_findings(tools=["semgrep"])
        with factory.connect() as conn:
            rows = conn.execute("SELECT tool FROM findings").fetchall()
        tools = [r["tool"] for r in rows]
        assert "semgrep" not in tools
        assert "gitleaks" in tools

    def test_delete_by_tool_keeps_runs(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(
            run_repo,
            repo,
            [{"tool": "semgrep", "severity": "high", "file_path": "foo.py"}],
        )
        repo.delete_findings(tools=["semgrep"])
        with factory.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] >= 1


# ---------------------------------------------------------------------------
# get_finding / get_findings
# ---------------------------------------------------------------------------


class TestGetFinding:
    def test_returns_dict(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(run_repo, repo, [{"tool": "nmap", "severity": "low"}])
        with repo._factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]
        result = repo.get_finding(fid)
        assert isinstance(result, dict)
        assert result["tool"] == "nmap"

    def test_returns_none_for_missing(self, repo: FindingRepository) -> None:
        assert repo.get_finding(999_999) is None


# ---------------------------------------------------------------------------
# get_tool_meta_keys
# ---------------------------------------------------------------------------


class TestGetToolMetaKeys:
    def test_returns_zero_count_for_unknown_tool(self, repo: FindingRepository) -> None:
        count, keys = repo.get_tool_meta_keys("nonexistent")
        assert count == 0
        assert keys == set()

    def test_returns_meta_keys(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [{"tool": "semgrep", "risk_type": "sqli", "file_path": "a.py"}],
        )
        count, keys = repo.get_tool_meta_keys("semgrep")
        assert count == 1
        assert "risk_type" in keys


# ---------------------------------------------------------------------------
# search — finding_type json_each filter (real SQLite)
# ---------------------------------------------------------------------------


class TestFindingTypeJsonEach:
    def test_exact_match_secret_does_not_return_vulnerability(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
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
        results = repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["finding_type"] == ["secret"] for r in results)
        assert not any(r["metadata"].get("tool") == "semgrep" for r in results)

    def test_exact_match_multi_value(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {"tool": "gitleaks", "rule_id": "r1", "finding_type": "secret"},
                {"tool": "semgrep", "rule_id": "r2", "finding_type": "vulnerability"},
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                },
            ],
        )
        results = repo.search(
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

    def test_partial_match_vuln(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {"tool": "semgrep", "rule_id": "r2", "finding_type": "vulnerability"},
                {"tool": "gitleaks", "rule_id": "r1", "finding_type": "secret"},
            ],
        )
        results = repo.search(
            {
                "conditions": [("finding_type", "~=", ["vuln"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all(r["metadata"]["tool"] == "semgrep" for r in results)

    def test_exact_match_empty_result(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                }
            ],
        )
        results = repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert results == []


# ---------------------------------------------------------------------------
# update_finding
# ---------------------------------------------------------------------------


class TestUpdateFinding:
    _VALID_UPDATE = {
        "confidence": "probable",
        "finding_type": "vulnerability",
        "severity": "high",
        "reasoning": "Code review confirms taint flow.",
        "remediation": "Parameterise the query.",
        "attack_vector": "network",
        "call_stack": None,
        "strategy": "manual",
    }

    def test_updates_row(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {
                    "tool": "semgrep",
                    "severity": "medium",
                    "confidence": "potential",
                    "file_path": "a.py",
                }
            ],
        )
        with factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]

        result = repo.update_finding(fid, **self._VALID_UPDATE)
        assert result is True

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT confidence, severity, triaged_by FROM findings WHERE id = ?",
                (fid,),
            ).fetchone()
        assert row["confidence"] == "probable"
        assert row["severity"] == "high"
        assert row["triaged_by"] == "claude-code"

    def test_raises_for_missing_id(self, repo: FindingRepository) -> None:
        with pytest.raises(ValueError, match="not found"):
            repo.update_finding(999_999, **self._VALID_UPDATE)

    def test_triage_block_in_meta(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "file_path": "a.py"}])
        with factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]

        repo.update_finding(fid, **self._VALID_UPDATE)

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT meta FROM findings WHERE id = ?", (fid,)
            ).fetchone()
        meta = json.loads(row["meta"])
        triage = meta["triage"]
        assert triage["confidence"] == "probable"
        assert triage["strategy"] == "manual"
        assert triage["triaged_by"] == "claude-code"
        assert "triaged_at" in triage

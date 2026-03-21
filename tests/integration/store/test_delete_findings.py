"""Integration tests for FindingRepository.delete_findings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration


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

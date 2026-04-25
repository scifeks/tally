"""Tests for FindingRepository upsert and delete operations."""

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
    finding_repo.insert_findings(run_id, findings)
    return run_id


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
            assert conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM run_tools").fetchone()[0] == 0

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
            assert conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] >= 1

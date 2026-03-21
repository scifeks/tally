"""Integration tests for RunRepository management helpers."""

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

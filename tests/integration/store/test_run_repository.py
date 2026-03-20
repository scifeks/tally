"""Tests for RunRepository."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


class TestCreateRun:
    def test_returns_int(self, repo: RunRepository) -> None:
        run_id = repo.create_run({"tool": "gitleaks"})
        assert isinstance(run_id, int)
        assert run_id >= 1

    def test_sequential_ids(self, repo: RunRepository) -> None:
        id1 = repo.create_run({})
        id2 = repo.create_run({})
        assert id2 > id1

    def test_args_persisted(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        import json

        run_id = repo.create_run({"tool": "semgrep", "version": "1.0"})
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT args FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        assert json.loads(row["args"]) == {"tool": "semgrep", "version": "1.0"}


class TestAddRunTools:
    def test_inserts_row_per_tool(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = repo.create_run({})
        repo.add_run_tools(
            run_id,
            [
                {"tool": "gitleaks", "findings_count": 3},
                {"tool": "semgrep", "findings_count": 1},
            ],
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT tool FROM run_tools WHERE run_id = ?", (run_id,)
            ).fetchall()
        tools = [r["tool"] for r in rows]
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert len(tools) == 2

    def test_findings_count_stored(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = repo.create_run({})
        repo.add_run_tools(run_id, [{"tool": "nmap", "findings_count": 5}])
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT findings_count FROM run_tools WHERE run_id = ?", (run_id,)
            ).fetchone()
        assert row["findings_count"] == 5


class TestAddRunRepos:
    def test_inserts_row_per_repo(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = repo.create_run({})
        repo.add_run_repos(run_id, ["repo-a", "repo-b", "repo-c"])
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT repo FROM run_repos WHERE run_id = ?", (run_id,)
            ).fetchall()
        assert len(rows) == 3
        names = {r["repo"] for r in rows}
        assert names == {"repo-a", "repo-b", "repo-c"}

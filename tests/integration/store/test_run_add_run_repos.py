"""Tests for RunRepository.add_run_repos."""

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

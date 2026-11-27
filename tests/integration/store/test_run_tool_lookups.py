"""Tests for the tool run lookups the DefectDojo sync reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "tally.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _run(repo: RunRepository) -> int:
    return repo.create(
        project_id=1, repo_ids=[], tool_ids=[], domains=[], skip_enrichment=False
    )


def _repository(factory: ConnectionFactory, name: str) -> int:
    with factory.connect() as conn:
        cur = conn.execute("INSERT INTO repositories (name) VALUES (?)", (name,))
        assert cur.lastrowid is not None
        return cur.lastrowid


class TestToolRunLookups:
    def test_latest_done_ignores_newer_runs_that_did_not_finish(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        shop = _repository(factory, "shop")
        done_run = _run(repo)
        repo.add_tool_run(
            run_id=done_run, tool="semgrep", repo_id=shop, service="api", status="done"
        )
        for status in ("failed", "skipped", "running"):
            repo.add_tool_run(
                run_id=_run(repo),
                tool="semgrep",
                repo_id=shop,
                service="api",
                status=status,
            )
        assert (
            repo.latest_done_run_id(repo_id=shop, service="api", tool="semgrep")
            == done_run
        )

    def test_latest_done_matches_service_exactly(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        shop = _repository(factory, "shop")
        run_id = _run(repo)
        repo.add_tool_run(
            run_id=run_id, tool="semgrep", repo_id=shop, service="api", status="done"
        )
        repo.add_tool_run(run_id=run_id, tool="claudecode", repo_id=shop, status="done")
        assert (
            repo.latest_done_run_id(repo_id=shop, service="ui", tool="semgrep") is None
        )
        assert (
            repo.latest_done_run_id(repo_id=shop, service=None, tool="claudecode")
            == run_id
        )

    def test_pairs_cover_every_state_once(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        shop = _repository(factory, "shop")
        run_id = _run(repo)
        repo.add_tool_run(
            run_id=run_id, tool="semgrep", repo_id=shop, service="api", status="done"
        )
        repo.add_tool_run(
            run_id=run_id, tool="semgrep", repo_id=shop, service="ui", status="failed"
        )
        repo.add_tool_run(run_id=run_id, tool="burp")
        assert repo.list_repo_tool_pairs(run_id) == [(None, "burp"), (shop, "semgrep")]

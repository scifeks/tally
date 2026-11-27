"""Tests for RunRepository tool run rows."""

from __future__ import annotations

import json
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


def _run(repo: RunRepository, status: str = "running") -> int:
    return repo.create(
        project_id=1,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
        status=status,
    )


def _repository(factory: ConnectionFactory, name: str) -> int:
    with factory.connect() as conn:
        cur = conn.execute("INSERT INTO repositories (name) VALUES (?)", (name,))
        assert cur.lastrowid is not None
        return cur.lastrowid


class TestToolRunRows:
    def test_row_round_trips_with_repo_name_joined(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = _run(repo)
        repo_id = _repository(factory, "shop")
        repo.add_tool_run(
            run_id=run_id,
            tool="semgrep",
            repo_id=repo_id,
            service="api",
            domain="code",
            started_at="2026-01-01T00:00:00+00:00",
        )
        bundle = repo.get_with_tool_runs(run_id)
        assert bundle is not None
        row = bundle[1][0]
        assert (row.repo_id, row.repo_name, row.service) == (repo_id, "shop", "api")
        assert row.status == "running"

    def test_null_repo_row_has_no_repo_name(self, repo: RunRepository) -> None:
        run_id = _run(repo)
        repo.add_tool_run(run_id=run_id, tool="burp")
        bundle = repo.get_with_tool_runs(run_id)
        assert bundle is not None
        row = bundle[1][0]
        assert (row.repo_id, row.repo_name, row.service) == (None, None, None)

    def test_unknown_status_is_rejected(self, repo: RunRepository) -> None:
        run_id = _run(repo)
        with pytest.raises(ValueError):
            repo.add_tool_run(run_id=run_id, tool="semgrep", status="queued")

    def test_update_sets_only_given_fields(self, repo: RunRepository) -> None:
        run_id = _run(repo)
        row_id = repo.add_tool_run(run_id=run_id, tool="semgrep")
        repo.update_tool_run(
            row_id, status="failed", reason="not installed", exit_code=1
        )
        bundle = repo.get_with_tool_runs(run_id)
        assert bundle is not None
        row = bundle[1][0]
        assert (row.status, row.reason, row.exit_code) == (
            "failed",
            "not installed",
            1,
        )
        assert row.findings_count == 0

    def test_delete_removes_the_row(self, repo: RunRepository) -> None:
        run_id = _run(repo)
        row_id = repo.add_tool_run(run_id=run_id, tool="semgrep")
        repo.delete_tool_run(row_id)
        bundle = repo.get_with_tool_runs(run_id)
        assert bundle is not None
        assert bundle[1] == []

    def test_fail_running_leaves_finished_rows_alone(self, repo: RunRepository) -> None:
        run_id = _run(repo)
        repo.add_tool_run(run_id=run_id, tool="semgrep", status="done")
        repo.add_tool_run(run_id=run_id, tool="gitleaks")
        changed = repo.fail_running_tool_runs(run_id, "scan cancelled")
        bundle = repo.get_with_tool_runs(run_id)
        assert bundle is not None
        by_tool = {r.tool: (r.status, r.reason) for r in bundle[1]}
        assert changed == 1
        assert by_tool == {
            "semgrep": ("done", None),
            "gitleaks": ("failed", "scan cancelled"),
        }

    def test_stale_sweep_fails_running_tool_rows(self, repo: RunRepository) -> None:
        run_id = _run(repo, status="running")
        repo.add_tool_run(run_id=run_id, tool="semgrep")
        repo.mark_stale_runs_failed()
        bundle = repo.get_with_tool_runs(run_id)
        assert bundle is not None
        assert (bundle[1][0].status, bundle[1][0].reason) == (
            "failed",
            "scan interrupted",
        )

    def test_snapshots_are_stored_on_the_run_row(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
            arg_profile_snapshots={"zap": '[{"name": "--cmd", "type": "flag"}]'},
        )
        with factory.connect() as conn:
            stored = conn.execute(
                "SELECT arg_profile_snapshots FROM scan_runs WHERE id = ?",
                (run_id,),
            ).fetchone()[0]
        assert json.loads(stored) == {"zap": [{"name": "--cmd", "type": "flag"}]}

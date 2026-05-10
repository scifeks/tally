"""Tests for RunRepository.mark_stale_runs_failed."""

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


def _create(repo: RunRepository, status: str) -> int:
    return repo.create(
        project_id=1,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
        args=None,
        status=status,
    )


def test_marks_running_as_failed(
    factory: ConnectionFactory, repo: RunRepository
) -> None:
    run_id = _create(repo, "running")
    count = repo.mark_stale_runs_failed()
    assert count == 1
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT status, finished_at FROM scan_runs WHERE id = ?", (run_id,)
        ).fetchone()
    assert row["status"] == "failed"
    assert row["finished_at"] is not None


def test_marks_cancelling_as_failed(
    factory: ConnectionFactory, repo: RunRepository
) -> None:
    run_id = _create(repo, "cancelling")
    count = repo.mark_stale_runs_failed()
    assert count == 1
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT status FROM scan_runs WHERE id = ?", (run_id,)
        ).fetchone()
    assert row["status"] == "failed"


def test_leaves_terminal_states_untouched(
    factory: ConnectionFactory, repo: RunRepository
) -> None:
    done_id = _create(repo, "done")
    failed_id = _create(repo, "failed")
    cancelled_id = _create(repo, "cancelled")

    count = repo.mark_stale_runs_failed()
    assert count == 0

    with factory.connect() as conn:
        statuses = {
            r["id"]: r["status"]
            for r in conn.execute("SELECT id, status FROM scan_runs").fetchall()
        }
    assert statuses[done_id] == "done"
    assert statuses[failed_id] == "failed"
    assert statuses[cancelled_id] == "cancelled"


def test_preserves_existing_finished_at(
    factory: ConnectionFactory, repo: RunRepository
) -> None:
    """A row with finished_at already set is treated as terminal."""
    run_id = _create(repo, "running")
    repo.set_finished_at(run_id, "2026-04-29T12:00:00Z")

    count = repo.mark_stale_runs_failed()
    assert count == 0

    with factory.connect() as conn:
        row = conn.execute(
            "SELECT status, finished_at FROM scan_runs WHERE id = ?", (run_id,)
        ).fetchone()
    assert row["status"] == "running"  # unchanged
    assert row["finished_at"] == "2026-04-29T12:00:00Z"


def test_zero_rows_when_table_empty(repo: RunRepository) -> None:
    assert repo.mark_stale_runs_failed() == 0

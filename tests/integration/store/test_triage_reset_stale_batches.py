"""Tests for TriageBatchRepository.reset_stale_batches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import TriageBatchRepository  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> TriageBatchRepository:
    return TriageBatchRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _seed_batch(
    factory: ConnectionFactory,
    run_repo: RunRepository,
    status: str = "pending",
    attempts: int = 0,
) -> int:
    run_id = run_repo.create_run({})
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                json.dumps([1, 2]),
                json.dumps([{"id": 1}, {"id": 2}]),
                status,
                attempts,
            ),
        )
    return run_id


class TestResetStaleBatches:
    def test_resets_in_progress_to_pending(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="in_progress")
        count = repo.reset_stale_batches(run_id)
        assert count == 1
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE run_id = ?", (run_id,)
            ).fetchone()
        assert row["status"] == "pending"

    def test_does_not_touch_other_run(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_a = _seed_batch(factory, run_repo, status="in_progress")
        run_b = _seed_batch(factory, run_repo, status="in_progress")
        repo.reset_stale_batches(run_a)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE run_id = ?", (run_b,)
            ).fetchone()
        assert row["status"] == "in_progress"

"""Integration tests for triage batch atomic claim operations."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from domain.triage.entry import TriageBatchRow
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(
        tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    )
    f.init_schema()
    return f


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def triage_repo(
    factory: ConnectionFactory,
) -> TriageBatchRepository:
    return TriageBatchRepository(factory)


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


class TestAtomicBatchClaim:
    def test_claim_sets_in_progress_increments_attempts_sets_started_at(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        result = triage_repo.claim_batch(run_id)
        assert result is not None
        assert result.status == "in_progress"
        assert result.run_attempts == 1
        assert result.started_at is not None

    def test_two_concurrent_claims_no_duplication(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        results: list[TriageBatchRow | None] = [None, None]

        def _claim(idx: int) -> None:
            results[idx] = triage_repo.claim_batch(run_id)

        t1 = threading.Thread(target=_claim, args=(0,))
        t2 = threading.Thread(target=_claim, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1, "exactly one thread should have claimed the batch"

    def test_no_pending_batches_returns_none(
        self,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_id = run_repo.create_run({})
        result = triage_repo.claim_batch(run_id)
        assert result is None

    def test_high_attempt_count_still_claimable(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="pending", attempts=5)
        result = triage_repo.claim_batch(run_id)
        assert result is not None
        assert result.run_attempts == 6

    def test_complete_success_sets_status_and_completed_at(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = triage_repo.claim_batch(run_id)
        assert batch is not None

        triage_repo.complete_batch(batch.id, "success")

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch.id,),
            ).fetchone()
        assert row["status"] == "success"
        assert row["completed_at"] is not None

    def test_complete_failed_sets_status_and_completed_at(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = triage_repo.claim_batch(run_id)
        assert batch is not None

        triage_repo.complete_batch(batch.id, "failed")

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch.id,),
            ).fetchone()
        assert row["status"] == "failed"
        assert row["completed_at"] is not None

    def test_claim_scoped_to_correct_run_id(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
    ) -> None:
        run_a = run_repo.create_run({})
        run_b = _seed_batch(factory, run_repo)

        result = triage_repo.claim_batch(run_a)
        assert result is None

        result_b = triage_repo.claim_batch(run_b)
        assert result_b is not None
        assert result_b.run_id == run_b

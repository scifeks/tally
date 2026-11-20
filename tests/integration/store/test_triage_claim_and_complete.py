"""Tests for TriageBatchRepository claim_batch and complete_batch."""

from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from domain.triage.entry import TriageBatchRow  # noqa: E402
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


class TestClaimAndComplete:
    def test_claim_sets_in_progress_increments_attempts(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        result = repo.claim_batch(run_id)
        assert result is not None
        assert result.status == "in_progress"
        assert result.run_attempts == 1
        assert result.started_at is not None

    def test_two_concurrent_claims_no_duplication(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        results: list[TriageBatchRow | None] = [None, None]

        def _claim(idx: int) -> None:
            results[idx] = repo.claim_batch(run_id)

        t1 = threading.Thread(target=_claim, args=(0,))
        t2 = threading.Thread(target=_claim, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1

    def test_no_pending_batches_returns_none(
        self, repo: TriageBatchRepository, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create_run({})
        assert repo.claim_batch(run_id) is None

    def test_high_attempt_count_still_claimable(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="pending", attempts=5)
        result = repo.claim_batch(run_id)
        assert result is not None
        assert result.run_attempts == 6

    def test_complete_success(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "completed")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch.id,),
            ).fetchone()
        assert row["status"] == "completed"
        assert row["completed_at"] is not None

    def test_complete_failed(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "failed")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE id = ?", (batch.id,)
            ).fetchone()
        assert row["status"] == "failed"

    def test_claim_scoped_to_correct_run_id(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_a = run_repo.create_run({})
        run_b = _seed_batch(factory, run_repo)
        assert repo.claim_batch(run_a) is None
        result_b = repo.claim_batch(run_b)
        assert result_b is not None
        assert result_b.run_id == run_b


class TestExecutionTracking:
    """Verify that claim/complete dual-write to triage_batch_executions."""

    def test_claim_inserts_execution_row(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        claim = repo.claim_batch(run_id, usage_pool="plan")
        assert claim is not None
        assert claim.execution_id is not None
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, usage_pool, attempt_number"
                " FROM triage_batch_executions"
                " WHERE batch_id = ? AND attempt_number = 1",
                (claim.id,),
            ).fetchone()
        assert row is not None
        assert row["status"] == "in_progress"
        assert row["usage_pool"] == "plan"
        assert row["attempt_number"] == 1

    def test_second_attempt_increments_number(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        first = repo.claim_batch(run_id, usage_pool="plan")
        assert first is not None
        repo.complete_batch(first.id, "failed", error_class="RATE_LIMIT_PLAN")
        # Re-seed as pending so the legacy status check allows re-claim.
        with factory.connect() as conn:
            conn.execute(
                "UPDATE triage_batches SET status = 'pending' WHERE id = ?",
                (first.id,),
            )
        second = repo.claim_batch(run_id, usage_pool="api")
        assert second is not None
        assert second.execution_id != first.execution_id
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT MAX(attempt_number)"
                " FROM triage_batch_executions WHERE batch_id = ?",
                (first.id,),
            ).fetchone()
        assert row[0] == 2

    def test_complete_updates_execution_row(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "completed")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, finished_at FROM triage_batch_executions WHERE id = ?",
                (batch.execution_id,),
            ).fetchone()
        assert row["status"] == "completed"
        assert row["finished_at"] is not None

    def test_complete_stores_error_class(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "failed", error_class="RATE_LIMIT_PLAN")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT error_class FROM triage_batch_executions WHERE id = ?",
                (batch.execution_id,),
            ).fetchone()
        assert row["error_class"] == "RATE_LIMIT_PLAN"

    def test_claim_without_usage_pool_stores_null(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        claim = repo.claim_batch(run_id)
        assert claim is not None
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT usage_pool FROM triage_batch_executions WHERE id = ?",
                (claim.execution_id,),
            ).fetchone()
        assert row["usage_pool"] is None


class TestResetForResumeExecutionCleanup:
    """Verify reset_for_resume cancels active execution rows."""

    def test_reset_cancels_in_progress_execution(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None

        flipped = repo.reset_for_resume(run_id)
        assert flipped == 1

        with factory.connect() as conn:
            exec_row = conn.execute(
                "SELECT status, finished_at FROM triage_batch_executions"
                " WHERE batch_id = ? ORDER BY attempt_number DESC LIMIT 1",
                (batch.id,),
            ).fetchone()
        assert exec_row["status"] == "cancelled"
        assert exec_row["finished_at"] is not None

    def test_reset_allows_clean_reclaim(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        """After reset, the next claim creates attempt 2 without a stale attempt 1."""
        run_id = _seed_batch(factory, run_repo)
        first = repo.claim_batch(run_id)
        assert first is not None

        repo.reset_for_resume(run_id)
        second = repo.claim_batch(run_id)
        assert second is not None

        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT attempt_number, status FROM triage_batch_executions"
                " WHERE batch_id = ? ORDER BY attempt_number",
                (first.id,),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0]["status"] == "cancelled"
        assert rows[1]["status"] == "in_progress"


class TestCancelRemainingExecutionCleanup:
    """Verify cancel_remaining closes open execution rows."""

    def test_cancel_remaining_closes_in_progress_execution(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None

        cancelled = repo.cancel_remaining(run_id)
        assert cancelled == 1

        with factory.connect() as conn:
            exec_row = conn.execute(
                "SELECT status, finished_at FROM triage_batch_executions"
                " WHERE batch_id = ?",
                (batch.id,),
            ).fetchone()
        assert exec_row["status"] == "cancelled"
        assert exec_row["finished_at"] is not None

    def test_cancel_remaining_handles_pending_batch_without_execution(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        """Pending batches have no execution rows; cancel_remaining still works."""
        run_id = _seed_batch(factory, run_repo)
        cancelled = repo.cancel_remaining(run_id)
        assert cancelled == 1

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        assert row["status"] == "cancelled"


class TestCompleteBatchNoOpWarning:
    """Verify complete_batch logs a WARNING when no in_progress execution exists."""

    def test_warns_when_no_in_progress_execution(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        # Get the batch id without claiming (no execution row in in_progress)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT id FROM triage_batches WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        batch_id = row["id"]

        with caplog.at_level(
            logging.WARNING,
            logger="infrastructure.store.repositories.triage",
        ):
            repo.complete_batch(batch_id, "completed")

        assert any("no in_progress execution row" in r.message for r in caplog.records)

        # Legacy batch status still transitions
        with factory.connect() as conn:
            batch_row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        assert batch_row["status"] == "completed"
        assert batch_row["completed_at"] is not None

    def test_no_exception_on_legacy_batch(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        """complete_batch does not raise even without any execution row."""
        run_id = _seed_batch(factory, run_repo)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT id FROM triage_batches WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        batch_id = row["id"]

        # Should not raise
        repo.complete_batch(batch_id, "failed")

        with factory.connect() as conn:
            batch_row = conn.execute(
                "SELECT status FROM triage_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        assert batch_row["status"] == "failed"

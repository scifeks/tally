"""Tests for TriageBatchRepository claim_batch and complete_batch."""

from __future__ import annotations

import json
import sys
import threading
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
        assert result["status"] == "in_progress"
        assert result["run_attempts"] == 1
        assert result["started_at"] is not None

    def test_two_concurrent_claims_no_duplication(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        results: list[dict | None] = [None, None]

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

    def test_exhausted_attempts_never_claimed(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="pending", attempts=3)
        assert repo.claim_batch(run_id) is None

    def test_complete_success(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch["id"], "success")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch["id"],),
            ).fetchone()
        assert row["status"] == "success"
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
        repo.complete_batch(batch["id"], "failed")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE id = ?", (batch["id"],)
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
        assert result_b["run_id"] == run_b

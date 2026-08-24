"""Integration test for skipped batch lifecycle."""

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
from infrastructure.store.repositories.triage import (  # noqa: E402
    TriageBatchRepository,
)

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


def _seed_batch(factory: ConnectionFactory, run_id: int) -> None:
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status,"
            " run_attempts)"
            " VALUES (?, ?, ?, 'pending', 0)",
            (run_id, json.dumps([1]), json.dumps([{"id": 1}])),
        )


class TestSkippedBatchStatus:
    def test_claim_then_skip_sets_status(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = run_repo.create_run({})
        _seed_batch(factory, run_id)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "skipped")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch.id,),
            ).fetchone()
        assert row["status"] == "skipped"
        assert row["completed_at"] is not None

    def test_skipped_appears_in_summary_counts(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = run_repo.create_run({})
        _seed_batch(factory, run_id)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "skipped")
        summary = repo.summarize_for_run(run_id)
        assert summary is not None
        assert summary.counts_by_status.get("skipped", 0) == 1
        assert summary.status == "done"

    def test_skipped_not_counted_in_processed_findings(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = run_repo.create_run({})
        _seed_batch(factory, run_id)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch.id, "skipped")
        summary = repo.summarize_for_run(run_id)
        assert summary is not None
        assert summary.total_findings == 1
        assert summary.processed_findings == 0

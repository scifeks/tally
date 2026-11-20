"""Integration test for TriageBatchRepository.start_failover_execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.triage import TriageBatchRepository  # noqa: E402
from tests.integration.store._helpers import make_connection  # noqa: E402

pytestmark = pytest.mark.integration


def _make_repo(tmp_path: Path) -> tuple[TriageBatchRepository, Path]:
    db_path = tmp_path / "t.db"
    conn = make_connection(db_path)
    conn.close()
    factory = ConnectionFactory(db_path)
    return TriageBatchRepository(factory), db_path


def test_failover_closes_old_and_opens_new_execution(tmp_path: Path) -> None:
    """Pre-state: 1 batch with 1 in_progress execution (plan).

    After start_failover_execution: old execution is rate_limited with
    finished_at set; new execution is in_progress with usage_pool=api
    and attempt_number incremented.
    """
    repo, db_path = _make_repo(tmp_path)

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute(
        "INSERT INTO triage_batches"
        " (id, run_id, finding_ids, batch_data, status, started_at)"
        " VALUES (1, 1, '[]', '[]', 'in_progress', datetime('now'))"
    )
    conn.execute(
        "INSERT INTO triage_batch_executions"
        " (batch_id, attempt_number, status, usage_pool, started_at)"
        " VALUES (1, 1, 'in_progress', 'plan', datetime('now'))"
    )
    conn.commit()

    new_exec_id, new_attempt = repo.start_failover_execution(1, "api")

    rows = conn.execute(
        "SELECT * FROM triage_batch_executions WHERE batch_id = 1"
        " ORDER BY attempt_number"
    ).fetchall()
    conn.close()

    assert len(rows) == 2

    old = dict(rows[0])
    assert old["attempt_number"] == 1
    assert old["status"] == "rate_limited"
    assert old["finished_at"] is not None
    assert old["usage_pool"] == "plan"

    new = dict(rows[1])
    assert new["attempt_number"] == 2
    assert new["status"] == "in_progress"
    assert new["usage_pool"] == "api"
    assert new["started_at"] is not None
    assert new["id"] == new_exec_id
    assert new_attempt == 2

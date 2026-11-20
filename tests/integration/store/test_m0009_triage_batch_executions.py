"""Integration tests for m0009: triage_batch_executions migration."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.migrations import m0009_triage_batch_executions  # noqa: E402
from tests.integration.store._helpers import (  # noqa: E402
    make_connection,
    seed_triage_batches,
)

pytestmark = pytest.mark.integration

# Minimal DDL for a pre-m0009 database (only what the migration needs).
_PRE_M0009_DDL = """\
CREATE TABLE IF NOT EXISTS triage_batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    finding_ids  JSON NOT NULL,
    batch_data   JSON NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    run_attempts INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    started_at   TEXT,
    completed_at TEXT
);
"""


def _make_pre_m0009_db(db_path: Path) -> sqlite3.Connection:
    """Create a database with only the triage_batches table (pre-m0009)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_PRE_M0009_DDL)
    return conn


def test_executions_table_created(tmp_path: Path) -> None:
    db = make_connection(tmp_path / "t.db")
    cur = db.execute(
        "SELECT sql FROM sqlite_master WHERE name='triage_batch_executions'"
    )
    row = cur.fetchone()
    assert row is not None
    assert "batch_id" in row[0]
    assert "attempt_number" in row[0]
    assert "usage_pool" in row[0]
    db.close()


def test_backfill_creates_one_execution_per_existing_batch(tmp_path: Path) -> None:
    db = _make_pre_m0009_db(tmp_path / "t.db")
    db.execute(
        "INSERT INTO triage_batches (id, run_id, finding_ids, batch_data, status)"
        " VALUES (1, 1, '[]', '[]', 'completed')"
    )
    db.execute(
        "INSERT INTO triage_batches (id, run_id, finding_ids, batch_data, status)"
        " VALUES (2, 1, '[]', '[]', 'pending')"
    )
    db.commit()

    m0009_triage_batch_executions.upgrade(db)
    db.commit()

    cur = db.execute(
        "SELECT COUNT(*) FROM triage_batch_executions WHERE batch_id IN (1, 2)"
    )
    assert cur.fetchone()[0] == 2
    db.close()


def test_backfill_copies_status_and_timestamps(tmp_path: Path) -> None:
    db = _make_pre_m0009_db(tmp_path / "t.db")
    db.execute(
        "INSERT INTO triage_batches"
        " (id, run_id, finding_ids, batch_data, status,"
        " started_at, completed_at)"
        " VALUES (1, 1, '[]', '[]', 'completed',"
        " '2026-10-31T10:00:00', '2026-10-31T11:00:00')"
    )
    db.commit()

    m0009_triage_batch_executions.upgrade(db)
    db.commit()

    cur = db.execute(
        "SELECT status, started_at, finished_at"
        " FROM triage_batch_executions WHERE batch_id = 1"
    )
    row = cur.fetchone()
    assert row[0] == "completed"
    assert row[1] == "2026-10-31T10:00:00"
    assert row[2] == "2026-10-31T11:00:00"
    db.close()


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    db = _make_pre_m0009_db(tmp_path / "t.db")
    db.execute(
        "INSERT INTO triage_batches (id, run_id, finding_ids, batch_data, status)"
        " VALUES (1, 1, '[]', '[]', 'pending')"
    )
    db.commit()

    m0009_triage_batch_executions.upgrade(db)
    db.commit()
    # Running the upgrade again should not duplicate execution rows.
    m0009_triage_batch_executions.upgrade(db)
    db.commit()

    cur = db.execute("SELECT COUNT(*) FROM triage_batch_executions WHERE batch_id = 1")
    assert cur.fetchone()[0] == 1
    db.close()


def test_view_reports_latest_status(tmp_path: Path) -> None:
    db = make_connection(tmp_path / "t.db")
    db.execute(
        "INSERT INTO triage_batches"
        " (id, run_id, finding_ids, batch_data, status)"
        " VALUES (10, 1, '[]', '[]', 'pending')"
    )
    db.execute(
        "INSERT INTO triage_batch_executions"
        " (batch_id, attempt_number, status, started_at)"
        " VALUES (10, 1, 'rate_limited', '2026-10-31T10:00:00')"
    )
    db.execute(
        "INSERT INTO triage_batch_executions"
        " (batch_id, attempt_number, status, started_at)"
        " VALUES (10, 2, 'completed', '2026-10-31T11:00:00')"
    )
    cur = db.execute(
        "SELECT latest_status FROM triage_batches_with_status WHERE id = 10"
    )
    assert cur.fetchone()[0] == "completed"
    db.close()


def test_seed_helper_creates_execution_rows(tmp_path: Path) -> None:
    db = make_connection(tmp_path / "t.db")
    seed_triage_batches(
        db,
        batches=[
            {"id": 1, "run_id": 1, "status": "completed"},
            {"id": 2, "run_id": 1, "status": "pending"},
        ],
    )
    cur = db.execute(
        "SELECT COUNT(*) FROM triage_batch_executions WHERE batch_id IN (1, 2)"
    )
    assert cur.fetchone()[0] == 2
    db.close()

"""Integration tests for m0010: scan_phase_executions and scan_configs."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from tests.integration.store._helpers import make_connection  # noqa: E402

pytestmark = pytest.mark.integration


def test_scan_phase_executions_table_exists(tmp_path: Path) -> None:
    db = make_connection(tmp_path / "s.db")
    cur = db.execute("SELECT sql FROM sqlite_master WHERE name='scan_phase_executions'")
    row = cur.fetchone()
    assert row is not None
    for col in ("run_id", "phase", "attempt_number", "status", "usage_pool"):
        assert col in row[0]
    db.close()


def test_scan_configs_table_exists(tmp_path: Path) -> None:
    db = make_connection(tmp_path / "s.db")
    cur = db.execute("SELECT sql FROM sqlite_master WHERE name='scan_configs'")
    row = cur.fetchone()
    assert row is not None
    for col in ("only_full_slugs_json", "exclude_full_slugs_json"):
        assert col in row[0]
    db.close()


def test_scan_phase_executions_unique_attempt_per_phase(tmp_path: Path) -> None:
    db = make_connection(tmp_path / "s.db")
    db.execute("INSERT INTO scan_runs (id, project_id) VALUES (1, 1)")
    db.execute(
        "INSERT INTO scan_phase_executions "
        "(run_id, phase, attempt_number, status, started_at) "
        "VALUES (1, 'recon', 1, 'completed', '2026-10-31T10:00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO scan_phase_executions "
            "(run_id, phase, attempt_number, status, started_at) "
            "VALUES (1, 'recon', 1, 'completed', '2026-10-31T10:00:00')"
        )
    db.close()

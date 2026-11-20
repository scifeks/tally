"""Add scan_phase_executions and scan_configs tables.

scan_phase_executions is the per-attempt execution log for scan phases.
scan_configs captures the family filter and adversarial opt-in for a run.
"""

from __future__ import annotations

import sqlite3

VERSION = 10


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scan_phase_executions (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
            phase TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            usage_pool TEXT,
            started_at TEXT,
            finished_at TEXT,
            error_class TEXT,
            error_detail_json TEXT,
            metadata_json TEXT,
            UNIQUE(run_id, phase, attempt_number)
        );

        CREATE INDEX IF NOT EXISTS idx_scan_phase_executions_run
            ON scan_phase_executions(run_id);

        CREATE INDEX IF NOT EXISTS idx_scan_phase_executions_phase
            ON scan_phase_executions(run_id, phase);

        CREATE TABLE IF NOT EXISTS scan_configs (
            run_id INTEGER PRIMARY KEY REFERENCES scan_runs(id) ON DELETE CASCADE,
            only_full_slugs_json TEXT,
            exclude_full_slugs_json TEXT,
            adversarial_verification INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )

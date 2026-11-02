"""Split triage_batches identity from execution attempts.

Adds triage_batch_executions and a triage_batches_with_status view that
joins each batch to its latest execution. Backfills one execution per
existing batch so the view keeps returning the same status call sites
have been reading.
"""

from __future__ import annotations

import sqlite3

VERSION = 8


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS triage_batch_executions (
            id INTEGER PRIMARY KEY,
            batch_id INTEGER NOT NULL
                REFERENCES triage_batches(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            usage_pool TEXT,
            started_at TEXT,
            finished_at TEXT,
            error_class TEXT,
            error_detail_json TEXT,
            UNIQUE(batch_id, attempt_number)
        );

        CREATE INDEX IF NOT EXISTS idx_triage_batch_executions_batch
            ON triage_batch_executions(batch_id);

        CREATE INDEX IF NOT EXISTS idx_triage_batch_executions_status
            ON triage_batch_executions(status);

        CREATE VIEW IF NOT EXISTS triage_batches_with_status AS
            SELECT
                b.*,
                (
                    SELECT e.status FROM triage_batch_executions e
                    WHERE e.batch_id = b.id
                    ORDER BY e.attempt_number DESC
                    LIMIT 1
                ) AS latest_status,
                (
                    SELECT e.usage_pool FROM triage_batch_executions e
                    WHERE e.batch_id = b.id
                    ORDER BY e.attempt_number DESC
                    LIMIT 1
                ) AS latest_usage_pool
            FROM triage_batches b;
        """
    )

    # Idempotent backfill: for any batch without an execution row,
    # insert one carrying the batch's current status and timestamps.
    conn.execute(
        """
        INSERT INTO triage_batch_executions
            (batch_id, attempt_number, status, started_at, finished_at)
        SELECT
            b.id, 1, b.status, b.started_at, b.completed_at
        FROM triage_batches b
        WHERE NOT EXISTS (
            SELECT 1 FROM triage_batch_executions e WHERE e.batch_id = b.id
        )
        """
    )

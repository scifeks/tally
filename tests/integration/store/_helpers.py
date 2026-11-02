"""Shared test helpers for store integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from infrastructure.store.connection import ConnectionFactory


def make_connection(db_path: Path) -> sqlite3.Connection:
    """Create a fully-initialized database and return a raw connection."""
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def seed_triage_batches(
    conn: sqlite3.Connection,
    batches: list[dict[str, object]],
) -> None:
    """Insert triage_batches rows and corresponding execution rows."""
    for batch in batches:
        conn.execute(
            "INSERT INTO triage_batches"
            " (id, run_id, finding_ids, batch_data, status)"
            " VALUES (:id, :run_id, :finding_ids, :batch_data, :status)",
            {
                "id": batch["id"],
                "run_id": batch.get("run_id"),
                "finding_ids": batch.get("finding_ids", "[]"),
                "batch_data": batch.get("batch_data", "[]"),
                "status": batch.get("status", "pending"),
            },
        )
        conn.execute(
            "INSERT INTO triage_batch_executions"
            " (batch_id, attempt_number, status)"
            " VALUES (?, 1, ?)",
            (batch["id"], batch.get("status", "pending")),
        )
    conn.commit()

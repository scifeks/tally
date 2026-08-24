"""Add duplicate_of column to findings for post-insert dedup (TAL-148)."""

from __future__ import annotations

import sqlite3

from infrastructure.store.migrations._helpers import add_column_if_missing

VERSION = 7


def upgrade(conn: sqlite3.Connection) -> None:
    add_column_if_missing(conn, "findings", "duplicate_of", "INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_duplicate_of ON findings(duplicate_of)"
    )

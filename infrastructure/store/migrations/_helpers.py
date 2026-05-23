"""Shared utilities for schema migrations."""

from __future__ import annotations

import sqlite3


def add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> bool:
    """Add a column to a table if it does not already exist."""
    existing = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column in existing:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    return True


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Return True if the table exists in the database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None

"""Add triage_provider column and migrate existing triaged_by values."""

from __future__ import annotations

import sqlite3

from infrastructure.store.migrations._helpers import add_column_if_missing

VERSION = 6
DESCRIPTION = "Add triage_provider column to findings"


def upgrade(conn: sqlite3.Connection) -> None:
    add_column_if_missing(conn, "findings", "triage_provider", "TEXT")
    conn.execute(
        "UPDATE findings SET triage_provider = 'anthropic',"
        " triaged_by = 'auto_triage'"
        " WHERE triaged_by = 'claudecode'"
    )
    conn.execute(
        "UPDATE findings SET triage_provider = 'opencode',"
        " triaged_by = 'auto_triage'"
        " WHERE triaged_by = 'opencode'"
    )
    conn.execute(
        "UPDATE findings SET triaged_by = 'manual' WHERE triaged_by = 'analyst_web'"
    )

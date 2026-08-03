"""Add mode column to chat_sessions."""

from __future__ import annotations

import sqlite3

from infrastructure.store.migrations._helpers import add_column_if_missing

VERSION = 5
DESCRIPTION = "Add mode column to chat_sessions"


def upgrade(conn: sqlite3.Connection) -> None:
    add_column_if_missing(
        conn,
        "chat_sessions",
        "mode",
        "TEXT NOT NULL DEFAULT 'all'",
    )

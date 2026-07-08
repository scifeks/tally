"""Add psalm_stubs configuration column to repositories."""

from __future__ import annotations

import sqlite3

from infrastructure.store.migrations._helpers import add_column_if_missing

VERSION = 4
DESCRIPTION = "Add psalm_stubs configuration column"

_COLUMNS: list[tuple[str, str]] = [
    (
        "psalm_stubs_json",
        "TEXT NOT NULL DEFAULT '[\"php_builtins\"]'",
    ),
]


def upgrade(conn: sqlite3.Connection) -> None:
    for col, defn in _COLUMNS:
        add_column_if_missing(conn, "repositories", col, defn)

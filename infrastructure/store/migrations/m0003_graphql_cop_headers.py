"""Add graphql-cop headers column to repositories."""

from __future__ import annotations

import sqlite3

from infrastructure.store.migrations._helpers import add_column_if_missing

VERSION = 3
DESCRIPTION = "Add graphql-cop headers column"

_COLUMNS: list[tuple[str, str]] = [
    ("graphql_cop_headers_json", "TEXT NOT NULL DEFAULT '{}'"),
]


def upgrade(conn: sqlite3.Connection) -> None:
    for col, defn in _COLUMNS:
        add_column_if_missing(conn, "repositories", col, defn)

"""Versioned schema migration runner for SQLite databases."""

from __future__ import annotations

import sqlite3
from types import ModuleType

from infrastructure.store.migrations import (
    m0001_baseline,
    m0002_service_scoped_overrides,
    m0003_graphql_cop_headers,
    m0004_psalm_stubs,
)
from infrastructure.store.migrations._helpers import (
    add_column_if_missing,
    table_exists,
)

__all__ = [
    "add_column_if_missing",
    "run_pending",
    "table_exists",
]

MIGRATIONS: list[ModuleType] = [
    m0001_baseline,
    m0002_service_scoped_overrides,
    m0003_graphql_cop_headers,
    m0004_psalm_stubs,
]


def run_pending(conn: sqlite3.Connection) -> int:
    """Run all pending migrations and return the count applied."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version    INTEGER NOT NULL,"
        "  applied_at TEXT NOT NULL"
        "    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
        ")"
    )

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] is not None else 0

    applied = 0
    for migration in sorted(MIGRATIONS, key=lambda m: m.VERSION):
        if migration.VERSION > current:
            migration.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (migration.VERSION,),
            )
            applied += 1

    return applied

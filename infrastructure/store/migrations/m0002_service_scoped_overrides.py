"""Add service-scoped tool overrides (scope, repo_id, service_name)."""

from __future__ import annotations

import sqlite3

VERSION = 2
DESCRIPTION = "Add service-scoped tool overrides"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE tool_overrides RENAME TO tool_overrides_old")

    conn.execute("""
        CREATE TABLE tool_overrides (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name           TEXT NOT NULL,
            args_mode           TEXT NOT NULL DEFAULT 'stock'
                                  CHECK (args_mode IN ('stock', 'custom')),
            type                TEXT NOT NULL
                                  CHECK (type IN ('repo', 'api')),
            location            TEXT NOT NULL
                                  CHECK (location IN ('local', 'docker')),
            path                TEXT,
            container_name      TEXT,
            container_tool_path TEXT,
            scope               TEXT NOT NULL DEFAULT 'global'
                                  CHECK (scope IN ('global', 'service')),
            repo_id             INTEGER,
            service_name        TEXT,
            created_at          TEXT NOT NULL
                                  DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL
                                  DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        INSERT INTO tool_overrides (
            id, tool_name, args_mode, type, location, path,
            container_name, container_tool_path, scope,
            created_at, updated_at
        )
        SELECT
            id, tool_name, args_mode, type, location, path,
            container_name, container_tool_path, 'global',
            created_at, updated_at
        FROM tool_overrides_old
    """)

    conn.execute("""
        CREATE UNIQUE INDEX uq_tool_overrides_global
            ON tool_overrides (tool_name)
            WHERE scope = 'global'
    """)
    conn.execute("""
        CREATE UNIQUE INDEX uq_tool_overrides_service
            ON tool_overrides (tool_name, repo_id, service_name)
            WHERE scope = 'service'
    """)

    conn.execute("DROP TABLE tool_overrides_old")

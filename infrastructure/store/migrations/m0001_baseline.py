"""Add columns missing from pre-TAL-94 repositories tables."""

from __future__ import annotations

import sqlite3

from infrastructure.store.migrations._helpers import add_column_if_missing

VERSION = 1
DESCRIPTION = "Add missing repositories columns from TAL-94 restructure"

_REPO_COLUMNS: list[tuple[str, str]] = [
    ("path", "TEXT NOT NULL DEFAULT ''"),
    ("docker_path", "TEXT NOT NULL DEFAULT ''"),
    ("container_name", "TEXT NOT NULL DEFAULT ''"),
    ("dependencies_file", "TEXT NOT NULL DEFAULT ''"),
    ("crawl_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("xsstrike_crawl_level", "INTEGER NOT NULL DEFAULT 10"),
    ("katana_headless", "INTEGER NOT NULL DEFAULT 0"),
    ("katana_depth", "INTEGER NOT NULL DEFAULT 5"),
    ("type_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("languages_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("base_urls_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("test_dirs_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("ignore_dirs_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("xsstrike_headers_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("dalfox_headers_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("katana_headers_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("auth_json", "TEXT"),
    ("url_seed_file", "TEXT"),
]


def upgrade(conn: sqlite3.Connection) -> None:
    """Add any missing columns to the repositories table."""
    for column, definition in _REPO_COLUMNS:
        add_column_if_missing(conn, "repositories", column, definition)

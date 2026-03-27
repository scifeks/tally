"""SQLite connection factory — shared infrastructure for all repositories."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class ConnectionFactory:
    """Creates SQLite connections and manages schema initialisation.

    Database path is fixed at construction time.  All repositories in
    ``infrastructure.store.repositories`` receive a ``ConnectionFactory`` in their
    ``__init__`` and call ``self._factory.connect()`` internally.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        """Return the absolute path to the database file."""
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        """Return an open SQLite connection (usable as a context manager)."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        """Create all tables and indexes if they do not exist."""
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    args       TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS run_tools (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id         INTEGER,
                    tool           TEXT,
                    findings_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS run_repos (
                    id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    repo   TEXT
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint      TEXT UNIQUE,
                    run_id           INTEGER,
                    tool             TEXT,
                    domain           TEXT,
                    segment          TEXT,
                    repo             TEXT,
                    finding_type     TEXT,
                    severity         TEXT,
                    confidence       TEXT,
                    file             TEXT,
                    rule_id          TEXT,
                    url              TEXT,
                    host             TEXT,
                    port             TEXT,
                    vulnerability_id TEXT,
                    package_name     TEXT,
                    ecosystem        TEXT,
                    description      TEXT,
                    package_version  TEXT,
                    cwe              TEXT,
                    enriched         INTEGER DEFAULT 0,
                    meta             TEXT DEFAULT '{}',
                    first_seen       TEXT,
                    last_seen        TEXT,
                    seen_count       INTEGER,
                    status           TEXT,
                    triaged_at       TEXT,
                    triaged_by       TEXT,
                    should_report    INTEGER NOT NULL DEFAULT 0,
                    business_impact  TEXT,
                    tal_id           TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_findings_tool
                    ON findings (tool);
                CREATE INDEX IF NOT EXISTS idx_findings_severity
                    ON findings (severity);
                CREATE INDEX IF NOT EXISTS idx_findings_fingerprint
                    ON findings (fingerprint);
                CREATE INDEX IF NOT EXISTS idx_findings_segment
                    ON findings (segment);
                CREATE INDEX IF NOT EXISTS idx_findings_repo
                    ON findings (repo);

                CREATE TABLE IF NOT EXISTS tool_audit_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name   TEXT    NOT NULL,
                    arguments   TEXT,
                    success     INTEGER NOT NULL DEFAULT 1,
                    error       TEXT,
                    duration_ms INTEGER,
                    called_at   TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_batches (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id       INTEGER,
                    finding_ids  JSON NOT NULL,
                    batch_data   JSON NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending',
                    run_attempts INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    started_at   TEXT,
                    completed_at TEXT
                );
            """)

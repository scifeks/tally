"""SQLite connection factory — shared infrastructure for all repositories."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
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

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager yielding an open SQLite connection, closed on exit."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # DDL shared between init_schema and _migrate_fingerprint_unique.
    _FINDINGS_COLUMNS = """
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint      TEXT,
                    run_id           INTEGER,
                    tool             TEXT,
                    domain           TEXT,
                    segment          TEXT,
                    repo             TEXT,
                    finding_type     TEXT,
                    severity         INTEGER,
                    confidence       TEXT,
                    file             TEXT,
                    rule_id          TEXT,
                    url              TEXT,
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
    """

    _FINDINGS_INDEXES = """
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
    """

    def init_schema(self) -> None:
        """Create all tables and indexes if they do not exist."""
        with self.connect() as conn:
            conn.executescript(f"""
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

                CREATE TABLE IF NOT EXISTS findings (
                    {self._FINDINGS_COLUMNS}
                );

                {self._FINDINGS_INDEXES}

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

                CREATE TABLE IF NOT EXISTS finding_history (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id        INTEGER NOT NULL
                                        REFERENCES findings(id) ON DELETE CASCADE,
                    timestamp         TEXT NOT NULL,
                    before_values     TEXT NOT NULL,
                    after_values      TEXT NOT NULL,
                    inference_context TEXT,
                    source            TEXT NOT NULL CHECK (source IN (
                                        'llm_inference',
                                        'auto_triage',
                                        'web_ui',
                                        'repl'
                                      ))
                );

                CREATE INDEX IF NOT EXISTS idx_finding_history_finding_id
                    ON finding_history (finding_id, timestamp DESC);
            """)
        self._migrate_fingerprint_unique()
        self._migrate_drop_run_repos()

    def _migrate_fingerprint_unique(self) -> None:
        """Remove the UNIQUE constraint on findings.fingerprint if present.

        Existing databases created before this fix have
        ``fingerprint TEXT UNIQUE``.  SQLite does not support
        ``ALTER TABLE DROP CONSTRAINT``, so the migration recreates the
        table without the constraint and copies all rows.

        The check uses ``PRAGMA index_list`` — rows with ``origin = 'u'``
        are unique constraints from the CREATE TABLE definition (not
        explicit CREATE UNIQUE INDEX statements).
        """
        with self.connect() as conn:
            idx_rows = conn.execute("PRAGMA index_list(findings)").fetchall()
            has_unique = any(row["origin"] == "u" for row in idx_rows)
            if not has_unique:
                return

        with self.connect() as conn:
            conn.executescript(f"""
                CREATE TABLE findings_new (
                    {self._FINDINGS_COLUMNS}
                );

                INSERT INTO findings_new SELECT * FROM findings;
                DROP TABLE findings;
                ALTER TABLE findings_new RENAME TO findings;

                {self._FINDINGS_INDEXES}
            """)

    def _migrate_drop_run_repos(self) -> None:
        """Drop the run_repos table if it still exists.

        The table was removed from the schema because it was never
        written to by any production code path — repo-level data is
        already available via the ``repo`` column on ``findings``.
        """
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_repos'"
            ).fetchone()
            if not exists:
                return
        with self.connect() as conn:
            conn.execute("DROP TABLE run_repos")

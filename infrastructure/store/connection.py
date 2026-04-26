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
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id      INTEGER,
                    args            TEXT,
                    created_at      TEXT,
                    status          TEXT,
                    started_at      TEXT,
                    finished_at     TEXT,
                    repo_ids        TEXT,
                    tool_ids        TEXT,
                    domains         TEXT,
                    skip_enrichment INTEGER,
                    findings_count  INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_scan_runs_project_id
                    ON scan_runs (project_id);
                CREATE INDEX IF NOT EXISTS idx_scan_runs_status
                    ON scan_runs (status);

                CREATE TABLE IF NOT EXISTS run_tools (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          INTEGER,
                    tool            TEXT,
                    findings_count  INTEGER DEFAULT 0,
                    repo            TEXT,
                    domain          TEXT,
                    status          TEXT,
                    started_at      TEXT,
                    finished_at     TEXT,
                    exit_code       INTEGER,
                    skip_reason     TEXT,
                    enriched_count  INTEGER,
                    total_to_enrich INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_run_tools_run_id
                    ON run_tools (run_id);

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

                CREATE TABLE IF NOT EXISTS reports (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id      INTEGER,
                    scan_run_id     INTEGER,
                    format          TEXT NOT NULL,
                    filename        TEXT NOT NULL,
                    filepath        TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'queued',
                    retention_tier  TEXT NOT NULL DEFAULT 'auto',
                    file_size_bytes INTEGER,
                    error           TEXT,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                    started_at      TEXT,
                    finished_at     TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_reports_project_created
                    ON reports (project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_reports_status
                    ON reports (status);

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

                CREATE TABLE IF NOT EXISTS drafts (
                    section           TEXT PRIMARY KEY,
                    status            TEXT NOT NULL,
                    original_filename TEXT,
                    generated_at      TEXT,
                    reviewed_at       TEXT
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id  INTEGER NOT NULL,
                    title       TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    expired_at  TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_chat_sessions_project_created
                    ON chat_sessions (project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_project_expired
                    ON chat_sessions (project_id, expired_at);

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  INTEGER NOT NULL
                                  REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content     TEXT NOT NULL,
                    model       TEXT,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages (session_id, id);
            """)
        self._migrate_fingerprint_unique()
        self._migrate_drop_run_repos()
        self._migrate_runs_to_scan_runs()
        self._migrate_extend_run_tools()

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

    def _migrate_runs_to_scan_runs(self) -> None:
        """Rename legacy ``runs`` table to ``scan_runs`` (Phase 5.1).

        Idempotent — safe to run on a fresh DB (only ``scan_runs`` exists),
        on a legacy DB (only ``runs`` exists at entry; ``init_schema`` has
        just created an empty ``scan_runs`` so both are present), and on
        an already-migrated DB (only ``scan_runs`` remains).
        """
        with self.connect() as conn:
            runs_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'"
            ).fetchone()
            if not runs_exists:
                return
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO scan_runs (id, args, created_at) "
                "SELECT id, args, created_at FROM runs"
            )
            conn.execute("DROP TABLE runs")

    def _migrate_extend_run_tools(self) -> None:
        """Add Phase 5.1 columns to ``run_tools`` if missing.

        Pre-existing databases were created when ``run_tools`` had only
        ``id``, ``run_id``, ``tool``, and ``findings_count``. Phase 5.1
        adds per-tool execution metadata (status, timestamps, exit_code,
        skip_reason, enrichment counters) and the ``repo`` / ``domain``
        dimensions findings already track.
        """
        new_columns = (
            ("repo", "TEXT"),
            ("domain", "TEXT"),
            ("status", "TEXT"),
            ("started_at", "TEXT"),
            ("finished_at", "TEXT"),
            ("exit_code", "INTEGER"),
            ("skip_reason", "TEXT"),
            ("enriched_count", "INTEGER"),
            ("total_to_enrich", "INTEGER"),
        )
        with self.connect() as conn:
            existing = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(run_tools)").fetchall()
            }
            for name, sqltype in new_columns:
                if name in existing:
                    continue
                conn.execute(f"ALTER TABLE run_tools ADD COLUMN {name} {sqltype}")

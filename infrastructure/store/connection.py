"""Create and manage SQLite connections for all repository classes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _migrate_repositories_to_services(conn: sqlite3.Connection) -> None:
    """Collapse flat repo columns into services_json for pre-TAL-143 databases."""
    cursor = conn.cursor()
    table_info = cursor.execute("PRAGMA table_info(repositories)").fetchall()
    column_names = {row[1] for row in table_info}

    if "docker_path" not in column_names:
        return

    rows = cursor.execute("SELECT * FROM repositories").fetchall()
    col_names = [description[0] for description in cursor.description]

    cursor.execute(
        """CREATE TABLE repositories_new (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            name                     TEXT NOT NULL,
            path                     TEXT NOT NULL DEFAULT '',
            services_json            TEXT NOT NULL DEFAULT '[]',
            xsstrike_crawl_level     INTEGER NOT NULL DEFAULT 10,
            katana_headless          INTEGER NOT NULL DEFAULT 0,
            katana_depth             INTEGER NOT NULL DEFAULT 5,
            xsstrike_headers_json    TEXT NOT NULL DEFAULT '{}',
            dalfox_headers_json      TEXT NOT NULL DEFAULT '{}',
            katana_headers_json      TEXT NOT NULL DEFAULT '{}',
            auth_json                TEXT,
            url_seed_file            TEXT,
            created_at               TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            ),
            deleted_at               TEXT
        )"""
    )

    for row in rows:
        row_dict = dict(zip(col_names, row))

        service_entry = {
            "name": "default",
            "relative_path": "",
            "type": json.loads(row_dict.get("type_json", "[]")),
            "languages": json.loads(row_dict.get("languages_json", "[]")),
            "docker_path": row_dict.get("docker_path", ""),
            "container_name": row_dict.get("container_name", ""),
            "base_urls": json.loads(row_dict.get("base_urls_json", "[]")),
            "test_dirs": json.loads(row_dict.get("test_dirs_json", "[]")),
            "ignore_dirs": json.loads(row_dict.get("ignore_dirs_json", "[]")),
            "dependencies_file": row_dict.get("dependencies_file", ""),
            "crawl_enabled": bool(row_dict.get("crawl_enabled", 1)),
        }

        cursor.execute(
            """INSERT INTO repositories_new (
                id, name, path, services_json,
                xsstrike_crawl_level, katana_headless, katana_depth,
                xsstrike_headers_json, dalfox_headers_json,
                katana_headers_json, auth_json, url_seed_file,
                created_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row_dict.get("id"),
                row_dict.get("name"),
                row_dict.get("path", ""),
                json.dumps([service_entry]),
                row_dict.get("xsstrike_crawl_level", 10),
                row_dict.get("katana_headless", 0),
                row_dict.get("katana_depth", 5),
                row_dict.get("xsstrike_headers_json", "{}"),
                row_dict.get("dalfox_headers_json", "{}"),
                row_dict.get("katana_headers_json", "{}"),
                row_dict.get("auth_json"),
                row_dict.get("url_seed_file"),
                row_dict.get("created_at"),
                row_dict.get("deleted_at"),
            ),
        )

    cursor.execute("DROP TABLE repositories")
    cursor.execute("ALTER TABLE repositories_new RENAME TO repositories")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_repositories_deleted "
        "ON repositories (deleted_at)"
    )


class ConnectionFactory:
    """Creates SQLite connections and manages schema initialization."""

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

    _FINDINGS_COLUMNS = """
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint      TEXT,
                    run_id           INTEGER,
                    tool             TEXT,
                    domain           TEXT,
                    segment          TEXT,
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
                    tal_id           TEXT,
                    repo_id          INTEGER
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
                CREATE INDEX IF NOT EXISTS idx_findings_repo_id
                    ON findings (repo_id);
    """

    PURGEABLE_TABLES: frozenset[str] = frozenset(
        {
            "findings",
            "finding_history",
            "scan_runs",
            "run_tools",
            "triage_batches",
            "tool_audit_log",
            "reports",
            "drafts",
            "chat_sessions",
            "chat_messages",
            "url_findings",
        }
    )

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
                    findings_count  INTEGER,
                    saved_scan_id   INTEGER REFERENCES saved_scans(id)
                                      ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scan_runs_project_id
                    ON scan_runs (project_id);
                CREATE INDEX IF NOT EXISTS idx_scan_runs_status
                    ON scan_runs (status);

                CREATE TABLE IF NOT EXISTS run_tools (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id               INTEGER,
                    tool                 TEXT,
                    findings_count       INTEGER DEFAULT 0,
                    repo                 TEXT,
                    domain               TEXT,
                    status               TEXT,
                    started_at           TEXT,
                    finished_at          TEXT,
                    exit_code            INTEGER,
                    skip_reason          TEXT,
                    enriched_count       INTEGER,
                    total_to_enrich      INTEGER,
                    arg_profile_snapshot TEXT
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
                    display_name    TEXT,
                    notes           TEXT,
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
                    reviewed_at       TEXT,
                    error             TEXT
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

                CREATE TABLE IF NOT EXISTS repositories (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    name                     TEXT NOT NULL,
                    path                     TEXT NOT NULL DEFAULT '',
                    services_json            TEXT NOT NULL DEFAULT '[]',
                    xsstrike_crawl_level     INTEGER NOT NULL DEFAULT 10,
                    katana_headless          INTEGER NOT NULL DEFAULT 0,
                    katana_depth             INTEGER NOT NULL DEFAULT 5,
                    xsstrike_headers_json    TEXT NOT NULL DEFAULT '{{}}',
                    dalfox_headers_json      TEXT NOT NULL DEFAULT '{{}}',
                    katana_headers_json      TEXT NOT NULL DEFAULT '{{}}',
                    auth_json                TEXT,
                    url_seed_file            TEXT,
                    created_at               TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                    ),
                    deleted_at               TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_repositories_deleted
                    ON repositories (deleted_at);

                CREATE TABLE IF NOT EXISTS url_findings (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_id     INTEGER NOT NULL,
                    source      TEXT NOT NULL,
                    tool        TEXT,
                    run_id      INTEGER,
                    method      TEXT NOT NULL,
                    protocol    TEXT NOT NULL,
                    host        TEXT NOT NULL,
                    port        INTEGER NOT NULL,
                    path        TEXT NOT NULL,
                    file_path   TEXT,
                    meta        TEXT NOT NULL DEFAULT '{{}}',
                    created_at  TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                    ),
                    CHECK (
                        (source = 'scan' AND tool IS NOT NULL
                         AND tool IN ('katana', 'noir'))
                        OR (source = 'user' AND tool IS NULL)
                    ),
                    FOREIGN KEY (repo_id) REFERENCES repositories(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (run_id) REFERENCES scan_runs(id)
                        ON DELETE SET NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uniq_url_findings
                    ON url_findings (
                        repo_id, source, COALESCE(tool, ''),
                        COALESCE(file_path, ''),
                        method, protocol, host, port, path
                    );
                CREATE INDEX IF NOT EXISTS idx_url_findings_repo_source
                    ON url_findings (repo_id, source);
                CREATE INDEX IF NOT EXISTS idx_url_findings_run
                    ON url_findings (run_id);

                CREATE TABLE IF NOT EXISTS tool_arg_profiles (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name  TEXT    NOT NULL,
                    name       TEXT    NOT NULL,
                    args       TEXT    NOT NULL DEFAULT '[]',
                    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE (tool_name, name)
                );

                CREATE INDEX IF NOT EXISTS idx_tool_arg_profiles_tool
                    ON tool_arg_profiles (tool_name);

                CREATE TABLE IF NOT EXISTS tool_overrides (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name           TEXT    NOT NULL,
                    args_mode           TEXT    NOT NULL DEFAULT 'stock'
                                          CHECK (args_mode IN ('stock', 'custom')),
                    type                TEXT    NOT NULL
                                          CHECK (type IN ('repo', 'api')),
                    location            TEXT    NOT NULL
                                          CHECK (location IN ('local', 'docker')),
                    path                TEXT,
                    container_name      TEXT,
                    container_tool_path TEXT,
                    scope               TEXT    NOT NULL DEFAULT 'global'
                                          CHECK (scope IN ('global', 'service')),
                    repo_id             INTEGER,
                    service_name        TEXT,
                    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_tool_overrides_global
                    ON tool_overrides (tool_name)
                    WHERE scope = 'global';
                CREATE UNIQUE INDEX IF NOT EXISTS uq_tool_overrides_service
                    ON tool_overrides (tool_name, repo_id, service_name)
                    WHERE scope = 'service';

                CREATE TABLE IF NOT EXISTS saved_scans (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT    NOT NULL UNIQUE,
                    skip_enrichment INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS saved_scan_repos (
                    saved_scan_id INTEGER NOT NULL
                                    REFERENCES saved_scans(id)  ON DELETE CASCADE,
                    repo_id       INTEGER NOT NULL
                                    REFERENCES repositories(id) ON DELETE CASCADE,
                    PRIMARY KEY (saved_scan_id, repo_id)
                );

                CREATE INDEX IF NOT EXISTS idx_saved_scan_repos_repo
                    ON saved_scan_repos (repo_id);

                CREATE TABLE IF NOT EXISTS saved_scan_tools (
                    saved_scan_id INTEGER NOT NULL
                                    REFERENCES saved_scans(id) ON DELETE CASCADE,
                    tool_name     TEXT    NOT NULL,
                    PRIMARY KEY (saved_scan_id, tool_name)
                );

                CREATE TABLE IF NOT EXISTS saved_scan_skip_tools (
                    saved_scan_id INTEGER NOT NULL
                                    REFERENCES saved_scans(id) ON DELETE CASCADE,
                    tool_name     TEXT    NOT NULL,
                    PRIMARY KEY (saved_scan_id, tool_name)
                );

                CREATE TABLE IF NOT EXISTS saved_scan_segments (
                    saved_scan_id INTEGER NOT NULL
                                    REFERENCES saved_scans(id) ON DELETE CASCADE,
                    segment       TEXT    NOT NULL
                                    CHECK (segment IN ('sast','sca','web','secrets')),
                    PRIMARY KEY (saved_scan_id, segment)
                );

                CREATE TABLE IF NOT EXISTS saved_scan_arg_profiles (
                    saved_scan_id  INTEGER NOT NULL
                                     REFERENCES saved_scans(id)
                                     ON DELETE CASCADE,
                    arg_profile_id INTEGER NOT NULL
                                     REFERENCES tool_arg_profiles(id)
                                     ON DELETE RESTRICT,
                    PRIMARY KEY (saved_scan_id, arg_profile_id)
                );

                CREATE INDEX IF NOT EXISTS idx_saved_scan_arg_profiles_profile
                    ON saved_scan_arg_profiles (arg_profile_id);
            """)
            from infrastructure.store.migrations import run_pending

            run_pending(conn)
            _migrate_repositories_to_services(conn)

    def purge_operational_tables(self) -> None:
        """Clear operational data tables, preserving configuration.

        AUTOINCREMENT counters are also reset. Foreign-key enforcement
        is suspended so deletion order does not matter.
        """
        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            for table in self.PURGEABLE_TABLES:
                conn.execute(f"DELETE FROM [{table}]")
            seq_exists = conn.execute(
                "SELECT 1 FROM sqlite_master"
                " WHERE type='table' AND name='sqlite_sequence'"
            ).fetchone()
            if seq_exists:
                for table in self.PURGEABLE_TABLES:
                    conn.execute(
                        "DELETE FROM sqlite_sequence WHERE name = ?",
                        (table,),
                    )

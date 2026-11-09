"""Add 'cli' to the finding_history source CHECK constraint."""

from __future__ import annotations

import sqlite3

VERSION = 8


def upgrade(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='finding_history'"
    ).fetchone()
    if row is None or "'cli'" in (row[0] or ""):
        return
    conn.executescript("""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE IF NOT EXISTS finding_history_new (
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
                                'repl',
                                'mcp_triage',
                                'cli'
                              ))
        );
        INSERT INTO finding_history_new
            SELECT * FROM finding_history;
        DROP TABLE finding_history;
        ALTER TABLE finding_history_new RENAME TO finding_history;
        CREATE INDEX IF NOT EXISTS idx_finding_history_finding_id
            ON finding_history (finding_id, timestamp DESC);
        PRAGMA foreign_keys = ON;
    """)

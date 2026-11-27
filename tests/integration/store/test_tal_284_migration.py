"""Tests for the one-time TAL-284 project database migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.store import tal_284_migration as migration

pytestmark = pytest.mark.integration

_OLD_SCHEMA = """
    CREATE TABLE scan_runs (id INTEGER PRIMARY KEY, args TEXT, status TEXT);
    CREATE TABLE run_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, tool TEXT,
        findings_count INTEGER DEFAULT 0, repo TEXT, domain TEXT, status TEXT,
        started_at TEXT, finished_at TEXT, exit_code INTEGER, skip_reason TEXT,
        enriched_count INTEGER, total_to_enrich INTEGER,
        arg_profile_snapshot TEXT
    );
    CREATE TABLE repositories (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
        services_json TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE findings (
        id INTEGER PRIMARY KEY, tool TEXT, repo_id INTEGER, description TEXT
    );
    INSERT INTO scan_runs (id, status) VALUES (1, 'done');
    INSERT INTO run_tools (run_id, tool, findings_count) VALUES (1, 'semgrep', 4);
    INSERT INTO repositories (id, name, services_json) VALUES
        (1, 'solo', '[{"name": "default"}]'),
        (2, 'mono', '[{"name": "api"}, {"name": "ui"}]');
    INSERT INTO findings (id, tool, repo_id, description) VALUES
        (1, 'semgrep', 1, 'kept'),
        (2, 'burp', 1, 'kept'),
        (3, 'semgrep', NULL, 'kept'),
        (4, 'semgrep', 2, 'kept'),
        (5, 'manual', 1, 'kept');
"""


def _project(base: Path, name: str = "shop") -> Path:
    sqlite_dir = base / "projects" / name / "sqlite"
    sqlite_dir.mkdir(parents=True)
    (sqlite_dir / "credentials.key").write_text("secret")
    conn = sqlite3.connect(sqlite_dir / "findings.db")
    conn.executescript(_OLD_SCHEMA)
    conn.close()
    return sqlite_dir.parent


def _rows(db_path: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestTal284Migration:
    def test_backs_up_the_sqlite_folder_before_changing_anything(
        self, tmp_path: Path
    ) -> None:
        project = _project(tmp_path)
        outcome = migration.migrate_project(project, "20261126T000000Z")
        backup = project / "sqlite.bak-tal-284-20261126T000000Z"
        assert outcome.status == "PASS"
        assert (backup / "credentials.key").read_text() == "secret"
        assert _rows(
            backup / "findings.db", "SELECT tool, findings_count FROM run_tools"
        ) == [("semgrep", 4)]

    def test_rebuilds_run_tools_and_adds_the_columns(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        migration.migrate_project(project, "s")
        db = project / "sqlite" / "findings.db"
        columns = {r[1] for r in _rows(db, "PRAGMA table_info(run_tools)")}
        assert {"repo_id", "service", "reason"} <= columns
        assert not {"repo", "skip_reason", "arg_profile_snapshot"} & columns
        assert _rows(db, "SELECT COUNT(*) FROM run_tools") == [(0,)]
        assert "arg_profile_snapshots" in {
            r[1] for r in _rows(db, "PRAGMA table_info(scan_runs)")
        }

    def test_backfills_service_only_where_it_is_unambiguous(
        self, tmp_path: Path
    ) -> None:
        project = _project(tmp_path)
        migration.migrate_project(project, "s")
        db = project / "sqlite" / "findings.db"
        assert _rows(
            db, "SELECT id, service, description FROM findings ORDER BY id"
        ) == [
            (1, "default", "kept"),
            (2, None, "kept"),
            (3, None, "kept"),
            (4, None, "kept"),
            (5, None, "kept"),
        ]

    def test_second_run_skips_and_takes_no_new_backup(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        migration.migrate_project(project, "first")
        outcome = migration.migrate_project(project, "second")
        assert outcome.status == "SKIP"
        assert not (project / "sqlite.bak-tal-284-second").exists()

    def test_failed_backup_leaves_the_database_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)

        def _fail(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(migration.shutil, "copytree", _fail)
        outcome = migration.migrate_project(project, "s")
        assert outcome.status == "FAIL"
        assert migration.needs_migration(project / "sqlite" / "findings.db")

    def test_exit_code_is_non_zero_when_a_project_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _project(tmp_path)

        def _fail(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(migration.shutil, "copytree", _fail)
        assert migration.main(["--base-path", str(tmp_path)]) == 1

    def test_backup_refuses_a_database_held_open_by_another_connection(
        self, tmp_path: Path
    ) -> None:
        project = _project(tmp_path)
        db = project / "sqlite" / "findings.db"
        setup = sqlite3.connect(db)
        setup.execute("PRAGMA journal_mode=WAL")
        setup.execute("INSERT INTO scan_runs (id, status) VALUES (2, 'done')")
        setup.commit()
        setup.close()
        holder = sqlite3.connect(db, isolation_level=None)
        holder.execute("BEGIN")
        holder.execute("SELECT * FROM run_tools").fetchall()
        writer = sqlite3.connect(db)
        writer.execute("INSERT INTO scan_runs (id, status) VALUES (3, 'done')")
        writer.commit()
        writer.close()
        try:
            outcome = migration.migrate_project(project, "s")
        finally:
            holder.close()
        assert outcome.status == "FAIL"
        assert "in use" in outcome.detail
        assert migration.needs_migration(db)

    def test_one_corrupt_project_does_not_stop_the_others(self, tmp_path: Path) -> None:
        _project(tmp_path, "good")
        bad = _project(tmp_path, "bad")
        (bad / "sqlite" / "findings.db").write_bytes(b"not a database" * 100)
        outcomes = {o.project: o.status for o in migration.migrate_all(tmp_path, "s")}
        assert outcomes == {"bad": "FAIL", "good": "PASS"}

    def test_failure_mid_migration_rolls_back_and_reports_the_backup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)
        monkeypatch.setattr(migration, "RUN_TOOLS_SCHEMA", "NOT VALID SQL")
        outcome = migration.migrate_project(project, "s")
        assert outcome.status == "FAIL"
        assert "migration rolled back" in outcome.detail
        assert "backup=" in outcome.detail
        assert migration.needs_migration(project / "sqlite" / "findings.db")

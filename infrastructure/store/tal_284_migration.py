"""One-time migration of project databases to per-service tool runs."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from infrastructure.store.connection import RUN_TOOLS_SCHEMA

_NULL_SERVICE_TOOLS = ("burp", "claudecode", "opencode", "manual")

_BACKFILL_SERVICE = f"""
    UPDATE findings
    SET service = (
        SELECT json_extract(r.services_json, '$[0].name')
        FROM repositories r WHERE r.id = findings.repo_id
    )
    WHERE repo_id IS NOT NULL
      AND tool NOT IN ({", ".join("?" for _ in _NULL_SERVICE_TOOLS)})
      AND (
        SELECT json_array_length(r.services_json)
        FROM repositories r WHERE r.id = findings.repo_id
      ) = 1
"""


@dataclass(frozen=True)
class ProjectOutcome:
    project: str
    status: str
    detail: str


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def needs_migration(db_path: Path) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        columns = _columns(conn, "run_tools")
    finally:
        conn.close()
    return bool(columns) and "service" not in columns


def _backup(sqlite_dir: Path, stamp: str) -> Path:
    db_path = sqlite_dir / "findings.db"
    # Folding the WAL into the main file first makes a plain copy complete.
    conn = sqlite3.connect(db_path)
    try:
        busy = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    finally:
        conn.close()
    # A busy checkpoint leaves the WAL unfolded, so a copy could be torn.
    wal_path = sqlite_dir / "findings.db-wal"
    if busy != 0 or (wal_path.exists() and wal_path.stat().st_size > 0):
        raise OSError(f"{db_path} is in use; stop Tally and retry")
    backup_dir = sqlite_dir.parent / f"sqlite.bak-tal-284-{stamp}"
    shutil.copytree(sqlite_dir, backup_dir)
    copied = backup_dir / "findings.db"
    if not copied.exists() or copied.stat().st_size != db_path.stat().st_size:
        raise OSError(f"backup of {db_path} is incomplete")
    return backup_dir


def _migrate_database(db_path: Path) -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("BEGIN")
        try:
            conn.execute("DROP TABLE run_tools")
            for statement in RUN_TOOLS_SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            if "service" not in _columns(conn, "findings"):
                conn.execute("ALTER TABLE findings ADD COLUMN service TEXT")
            if "arg_profile_snapshots" not in _columns(conn, "scan_runs"):
                conn.execute(
                    "ALTER TABLE scan_runs ADD COLUMN arg_profile_snapshots TEXT"
                )
            conn.execute(_BACKFILL_SERVICE, _NULL_SERVICE_TOOLS)
            conn.execute("COMMIT")
        except Exception:
            # SQLite may already have rolled back (disk full, I/O error).
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def migrate_project(project_root: Path, stamp: str) -> ProjectOutcome:
    name = project_root.name
    try:
        return _migrate_project(project_root, stamp)
    except Exception as exc:
        return ProjectOutcome(name, "FAIL", f"unexpected error: {exc}")


def _migrate_project(project_root: Path, stamp: str) -> ProjectOutcome:
    sqlite_dir = project_root / "sqlite"
    db_path = sqlite_dir / "findings.db"
    name = project_root.name
    if not db_path.exists() or not needs_migration(db_path):
        return ProjectOutcome(name, "SKIP", "nothing to migrate")
    try:
        backup_dir = _backup(sqlite_dir, stamp)
    except Exception as exc:
        return ProjectOutcome(name, "FAIL", f"backup failed, not migrated: {exc}")
    try:
        _migrate_database(db_path)
    except Exception as exc:
        return ProjectOutcome(
            name, "FAIL", f"migration rolled back: {exc}; backup={backup_dir}"
        )
    return ProjectOutcome(name, "PASS", f"backup={backup_dir}")


def migrate_all(base_path: Path, stamp: str) -> list[ProjectOutcome]:
    projects_dir = base_path / "projects"
    roots = sorted(p for p in projects_dir.iterdir() if p.is_dir())
    return [migrate_project(root, stamp) for root in roots]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Tally root containing the projects/ folder",
    )
    args = parser.parse_args(argv)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    outcomes = migrate_all(args.base_path, stamp)
    for outcome in outcomes:
        print(f"{outcome.status} {outcome.project}: {outcome.detail}")
    return 1 if any(o.status == "FAIL" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())

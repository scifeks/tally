"""Project registry — single source of truth for project existence and paths."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class ProjectRegistryRepository:
    """Repository over the `projects` table in tally.db."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
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

    def init_schema(self) -> None:
        """Create the projects table and indexes if missing. Idempotent."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL UNIQUE,
                    path        TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                    ),
                    archived_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_projects_name
                    ON projects (name);
                CREATE INDEX IF NOT EXISTS idx_projects_archived
                    ON projects (archived_at);
            """)

    def list_active(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, path, created_at, archived_at "
                "FROM projects WHERE archived_at IS NULL ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, path, created_at, archived_at "
                "FROM projects ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, project_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, path, created_at, archived_at "
                "FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_name(self, name: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, path, created_at, archived_at "
                "FROM projects WHERE name = ?",
                (name,),
            ).fetchone()
        return dict(row) if row else None

    def insert(self, name: str, path: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, path) VALUES (?, ?)",
                (name, path),
            )
            return int(cur.lastrowid or 0)

    def archive(self, name: str) -> None:
        now = _utc_iso_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET archived_at = ? WHERE name = ?",
                (now, name),
            )

    def unarchive(self, name: str, new_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET archived_at = NULL, path = ? WHERE name = ?",
                (new_path, name),
            )

    def rename(self, old: str, new: str, new_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name = ?, path = ? WHERE name = ?",
                (new, new_path, old),
            )

    def sync_from_filesystem(self, base_path: str) -> None:
        """Reconcile registry rows with directories under <base_path>/projects/."""
        on_disk = _scan_projects_dir(Path(base_path))
        existing = {row["name"]: row for row in self.list_all()}
        now = _utc_iso_now()

        with self._connect() as conn:
            for name, abs_path in on_disk.items():
                row = existing.get(name)
                if row is None:
                    conn.execute(
                        "INSERT INTO projects (name, path) VALUES (?, ?)",
                        (name, abs_path),
                    )
                elif row["archived_at"] is not None:
                    conn.execute(
                        "UPDATE projects SET archived_at = NULL, path = ? "
                        "WHERE name = ?",
                        (abs_path, name),
                    )
                elif row["path"] != abs_path:
                    conn.execute(
                        "UPDATE projects SET path = ? WHERE name = ?",
                        (abs_path, name),
                    )

            for name, row in existing.items():
                if name not in on_disk and row["archived_at"] is None:
                    conn.execute(
                        "UPDATE projects SET archived_at = ? WHERE name = ?",
                        (now, name),
                    )


def _utc_iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scan_projects_dir(base_path: Path) -> dict[str, str]:
    """Return {name: absolute_path_str} for valid project dirs under base."""
    from core.project_paths import ProjectPaths

    projects_dir = ProjectPaths.projects_dir(base_path)
    if not projects_dir.exists():
        return {}
    result: dict[str, str] = {}
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if not (entry / "config" / "project.json").exists():
            continue
        result[entry.name] = str(entry.resolve())
    return result

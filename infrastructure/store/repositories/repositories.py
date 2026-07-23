"""CRUD for the per-project repositories table.

Each row carries all Repository pydantic fields (scalars as columns;
list/dict fields and auth as TEXT-as-JSON), plus id, mutable name,
url_seed_file path, and created_at/deleted_at lifecycle stamps.

Soft deletion via deleted_at; list_active and get_by_name filter
deleted_at IS NULL by default.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.project_repo_repository import ProjectRepoRepositoryPort
from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import RepoAuth, Repository

if TYPE_CHECKING:
    import sqlite3

    from infrastructure.store.connection import ConnectionFactory


_DICT_FIELDS: tuple[str, ...] = (
    "xsstrike_headers",
    "dalfox_headers",
    "katana_headers",
    "graphql_cop_headers",
)

_ALL_COLUMNS: str = (
    "id, name, path, services_json, "
    "xsstrike_crawl_level, katana_headless, katana_depth, "
    "xsstrike_headers_json, dalfox_headers_json, "
    "katana_headers_json, graphql_cop_headers_json, "
    "psalm_stubs_json, "
    "auth_json, url_seed_file, "
    "created_at, deleted_at"
)


def _row_to_repository(row: sqlite3.Row) -> Repository:
    """Hydrate a Repository pydantic model from a ``repositories`` row."""
    services_raw = json.loads(row["services_json"])
    services = [RepoService(**s) for s in services_raw]
    fields: dict[str, Any] = {
        "name": row["name"],
        "path": row["path"],
        "services": services,
        "xsstrike_crawl_level": int(row["xsstrike_crawl_level"]),
        "katana_headless": bool(row["katana_headless"]),
        "katana_depth": int(row["katana_depth"]),
    }
    for field in _DICT_FIELDS:
        fields[field] = json.loads(row[f"{field}_json"])
    fields["psalm_stubs"] = json.loads(row["psalm_stubs_json"])
    auth_raw = row["auth_json"]
    fields["auth"] = RepoAuth(**json.loads(auth_raw)) if auth_raw else None
    repo = Repository(**fields)
    return repo.model_copy(
        update={
            "id": int(row["id"]),
            "url_seed_file": row["url_seed_file"],
        }
    )


def _repository_to_row(repo: Repository) -> dict[str, Any]:
    """Serialize a Repository for INSERT / UPDATE."""
    auth_dump = repo.auth.model_dump() if repo.auth is not None else None
    services_dump = [s.model_dump() for s in repo.services]
    return {
        "name": repo.name,
        "path": repo.path,
        "services_json": json.dumps(services_dump),
        "xsstrike_crawl_level": int(repo.xsstrike_crawl_level),
        "katana_headless": int(repo.katana_headless),
        "katana_depth": int(repo.katana_depth),
        "xsstrike_headers_json": json.dumps(repo.xsstrike_headers),
        "dalfox_headers_json": json.dumps(repo.dalfox_headers),
        "katana_headers_json": json.dumps(repo.katana_headers),
        "graphql_cop_headers_json": json.dumps(repo.graphql_cop_headers),
        "psalm_stubs_json": json.dumps(repo.psalm_stubs),
        "auth_json": json.dumps(auth_dump) if auth_dump is not None else None,
        "url_seed_file": repo.url_seed_file,
    }


class RepositoryRepository(ProjectRepoRepositoryPort):
    """CRUD for the ``repositories`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def list_active(self) -> list[Repository]:
        """Return active rows ordered by name (case-insensitive)."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                f"SELECT {_ALL_COLUMNS} FROM repositories "
                "WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [_row_to_repository(r) for r in rows]

    def list_all(self) -> list[Repository]:
        """Return every row, including soft-deleted ones, ordered by id."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                f"SELECT {_ALL_COLUMNS} FROM repositories ORDER BY id"
            ).fetchall()
        return [_row_to_repository(r) for r in rows]

    def get_by_id(self, repo_id: int) -> Repository | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                f"SELECT {_ALL_COLUMNS} FROM repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
        return _row_to_repository(row) if row else None

    def get_active_by_id(self, repo_id: int) -> Repository | None:
        """Return the row only if it is active (not soft-deleted)."""
        repo = self.get_by_id(repo_id)
        if repo is None:
            return None
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT deleted_at FROM repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
        if row is None or row["deleted_at"] is not None:
            return None
        return repo

    def get_by_name(self, name: str) -> Repository | None:
        """Return the active row with ``name``; None if absent or deleted."""
        with self._factory.connect() as conn:
            row = conn.execute(
                f"SELECT {_ALL_COLUMNS} FROM repositories "
                "WHERE name = ? AND deleted_at IS NULL",
                (name,),
            ).fetchone()
        return _row_to_repository(row) if row else None

    def find_id_by_name(self, name: str) -> int | None:
        """Return the active row's id for ``name``, else None."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT id FROM repositories WHERE name = ? AND deleted_at IS NULL",
                (name,),
            ).fetchone()
        return int(row["id"]) if row else None

    def is_deleted(self, repo_id: int) -> bool:
        """Return True if the row exists and is soft-deleted."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT deleted_at FROM repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
        return row is not None and row["deleted_at"] is not None

    def insert(self, repo: Repository) -> int:
        """Insert *repo* and return the new integer id."""
        cols = _repository_to_row(repo)
        cols["created_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        column_list = ", ".join(cols.keys())
        placeholders = ", ".join("?" for _ in cols)
        with self._factory.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO repositories ({column_list}) VALUES ({placeholders})",
                tuple(cols.values()),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    def update(self, repo_id: int, repo: Repository) -> None:
        """Replace every column for ``repo_id`` with *repo*'s field values."""
        cols = _repository_to_row(repo)
        assignments = ", ".join(f"{name} = ?" for name in cols)
        with self._factory.connect() as conn:
            conn.execute(
                f"UPDATE repositories SET {assignments} WHERE id = ?",
                (*cols.values(), repo_id),
            )

    def rename(self, repo_id: int, new_name: str) -> None:
        """Mutate the ``name`` column for *repo_id*."""
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE repositories SET name = ? WHERE id = ?",
                (new_name, repo_id),
            )

    def set_url_seed_file(self, repo_id: int, path: str | None) -> None:
        """Record the most-recent seed-file path (or clear it with None)."""
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE repositories SET url_seed_file = ? WHERE id = ?",
                (path, repo_id),
            )

    def soft_delete(self, repo_id: int, when: str | None = None) -> None:
        """Stamp ``deleted_at`` (idempotent for already-deleted rows)."""
        ts = when or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE repositories SET deleted_at = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                (ts, repo_id),
            )

    def restore(self, repo_id: int) -> None:
        """Clear ``deleted_at`` so the row appears in ``list_active`` again."""
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE repositories SET deleted_at = NULL WHERE id = ?",
                (repo_id,),
            )

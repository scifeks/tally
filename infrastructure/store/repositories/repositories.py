"""RepositoryRepository — manages the ``repositories`` table (Phase 9).

Each row maps a stable ``id`` and immutable ``uuid`` (the JSON-side
identifier persisted in ``project.json``) to a mutable ``name``. Repos
are soft-deleted via ``deleted_at``; ``find_id_by_name`` and
``list_active`` filter ``deleted_at IS NULL`` by default.

The companion JSON-side data (path, type, languages, base_urls, tool
flags, auth, etc.) continues to live in ``projects/<p>/config/project.json``
for Phase 9 — see roadmap Phase 13.3 for the full migration to DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


@dataclass(frozen=True)
class RepositoryRow:
    id: int
    uuid: str
    name: str
    created_at: str
    deleted_at: str | None


class RepositoryRepository:
    """CRUD for the ``repositories`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_active(self) -> list[RepositoryRow]:
        """Return all rows where ``deleted_at IS NULL``, ordered by name."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT id, uuid, name, created_at, deleted_at "
                "FROM repositories WHERE deleted_at IS NULL "
                "ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [RepositoryRow(**dict(r)) for r in rows]

    def list_all(self) -> list[RepositoryRow]:
        """Return every row, including soft-deleted ones."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT id, uuid, name, created_at, deleted_at "
                "FROM repositories ORDER BY id"
            ).fetchall()
        return [RepositoryRow(**dict(r)) for r in rows]

    def get_by_id(self, repo_id: int) -> RepositoryRow | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT id, uuid, name, created_at, deleted_at "
                "FROM repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
        return RepositoryRow(**dict(row)) if row else None

    def get_by_uuid(self, uuid: str) -> RepositoryRow | None:
        """Return the active row for *uuid*; None if absent or soft-deleted."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT id, uuid, name, created_at, deleted_at "
                "FROM repositories WHERE uuid = ? AND deleted_at IS NULL",
                (uuid,),
            ).fetchone()
        return RepositoryRow(**dict(row)) if row else None

    def get_by_uuid_including_deleted(self, uuid: str) -> RepositoryRow | None:
        """Return any row for *uuid*, including soft-deleted ones."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT id, uuid, name, created_at, deleted_at "
                "FROM repositories WHERE uuid = ?",
                (uuid,),
            ).fetchone()
        return RepositoryRow(**dict(row)) if row else None

    def get_by_name(self, name: str) -> RepositoryRow | None:
        """Return the active row with ``name``; None if absent or deleted."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT id, uuid, name, created_at, deleted_at "
                "FROM repositories WHERE name = ? AND deleted_at IS NULL",
                (name,),
            ).fetchone()
        return RepositoryRow(**dict(row)) if row else None

    def find_id_by_name(self, name: str) -> int | None:
        """Convenience: return the active row's ``id`` for *name*, else None."""
        row = self.get_by_name(name)
        return row.id if row else None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def insert(self, *, uuid: str, name: str) -> int:
        """Insert a new active row and return the new integer id."""
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO repositories (uuid, name) VALUES (?, ?)",
                (uuid, name),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def rename(self, repo_id: int, new_name: str) -> None:
        """Update the mutable ``name`` field for *repo_id*."""
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE repositories SET name = ? WHERE id = ?",
                (new_name, repo_id),
            )

    def soft_delete(self, repo_id: int, when: str | None = None) -> None:
        """Stamp ``deleted_at`` on *repo_id* (idempotent for already-deleted)."""
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

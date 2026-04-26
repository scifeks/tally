"""ChatSessionRepository — manages the ``chat_sessions`` table (Phase 8.1).

Each row represents one persistent UI chat session for a project.
Sessions are ``active`` while ``expired_at`` is NULL and become read-only
``expired`` archives once any scan run completes for the project (sealing
is wired in Phase 8.10).

Hard delete only: ``delete()`` removes the session and cascades to
``chat_messages`` via ``ON DELETE CASCADE`` (FK enforcement is enabled
at connection init via ``PRAGMA foreign_keys=ON``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


@dataclass(frozen=True)
class ChatSessionRow:
    id: int
    project_id: int
    title: str
    created_at: str
    updated_at: str
    expired_at: str | None


class ChatSessionRepository:
    """CRUD + retention helpers for the project-scoped ``chat_sessions`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def create(self, *, project_id: int, title: str) -> int:
        now = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO chat_sessions"
                " (project_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (project_id, title, now, now),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def touch(self, session_id: int, when: str | None = None) -> None:
        """Bump ``updated_at`` to *when* (defaults to now)."""
        ts = when or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (ts, session_id),
            )

    def mark_expired(
        self,
        session_ids: Iterable[int],
        when: str | None = None,
    ) -> None:
        """Set ``expired_at`` on every id in *session_ids* (already-expired
        rows are left untouched so the original sealing time survives).
        """
        ids = tuple(session_ids)
        if not ids:
            return
        ts = when or datetime.now(UTC).isoformat()
        placeholders = ",".join("?" for _ in ids)
        with self._factory.connect() as conn:
            conn.execute(
                f"UPDATE chat_sessions SET expired_at = ?"
                f" WHERE expired_at IS NULL AND id IN ({placeholders})",
                (ts, *ids),
            )

    def delete(self, session_id: int) -> None:
        with self._factory.connect() as conn:
            conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get(self, session_id: int) -> ChatSessionRow | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _row_to_session(row) if row else None

    def list_for_project(
        self,
        project_id: int,
        *,
        include_expired: bool = True,
    ) -> list[ChatSessionRow]:
        """Return sessions for *project_id*, newest first.

        When *include_expired* is False, rows with ``expired_at`` set are
        omitted (active-only view).
        """
        where = "project_id = ?"
        params: list[Any] = [project_id]
        if not include_expired:
            where += " AND expired_at IS NULL"
        with self._factory.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM chat_sessions WHERE {where} ORDER BY id DESC",
                tuple(params),
            ).fetchall()
        return [_row_to_session(r) for r in rows]

    def list_active_for_project(self, project_id: int) -> list[ChatSessionRow]:
        """Return active (non-expired) sessions for *project_id*, newest first."""
        return self.list_for_project(project_id, include_expired=False)

    def list_for_project_paginated(
        self,
        project_id: int,
        *,
        offset: int,
        limit: int,
        include_expired: bool = True,
    ) -> tuple[list[ChatSessionRow], int]:
        """Newest-first page of sessions plus total row count.

        Uses SQL ``LIMIT`` / ``OFFSET`` so the page does not require
        loading every row into memory. Returns ``(rows, total)``.
        """
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        where = "project_id = ?"
        params: list[Any] = [project_id]
        if not include_expired:
            where += " AND expired_at IS NULL"
        with self._factory.connect() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) FROM chat_sessions WHERE {where}",
                tuple(params),
            ).fetchone()
            total = int(total_row[0])
            rows = conn.execute(
                f"SELECT * FROM chat_sessions WHERE {where}"
                " ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [_row_to_session(r) for r in rows], total

    def list_expired_for_project(self, project_id: int) -> list[ChatSessionRow]:
        """Return expired sessions for *project_id*, newest first."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_sessions"
                " WHERE project_id = ? AND expired_at IS NOT NULL"
                " ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        return [_row_to_session(r) for r in rows]

    # ------------------------------------------------------------------
    # Phase 8.10 — retention sweep
    # ------------------------------------------------------------------
    def select_for_retention(
        self,
        project_id: int,
        *,
        keep: int,
    ) -> list[ChatSessionRow]:
        """Return expired rows beyond the *keep*-th most-recent.

        The caller deletes the returned rows; ``ON DELETE CASCADE`` removes
        their messages. Active sessions are never returned.
        """
        if keep < 0:
            raise ValueError("keep must be non-negative")
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_sessions"
                " WHERE project_id = ? AND expired_at IS NOT NULL"
                " ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        all_rows = [_row_to_session(r) for r in rows]
        if len(all_rows) <= keep:
            return []
        return all_rows[keep:]


def _row_to_session(row: Any) -> ChatSessionRow:
    return ChatSessionRow(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expired_at=row["expired_at"],
    )

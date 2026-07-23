"""Create, retrieve, and delete chat sessions scoped to a project.

Sessions are active while expired_at is NULL. Deletion cascades to
chat_messages via foreign-key constraint.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.chat_session_repository import ChatSessionRepositoryPort
from domain.chat.entry import ChatSessionRow

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


class ChatSessionRepository(ChatSessionRepositoryPort):
    """Create, read, and delete project-scoped chat sessions."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def create(self, *, project_id: int, title: str) -> int:
        now = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO chat_sessions"
                " (project_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (project_id, title, now, now),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

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

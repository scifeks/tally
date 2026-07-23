"""Persist and retrieve chat messages within a session.

Each row is one turn within a chat session. Role is either user or
assistant; model is the LLM model identifier on assistant turns and NULL
on user turns. Messages are append-only; deletion cascades from session
deletion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.chat_message_repository import ChatMessageRepositoryPort
from domain.chat.entry import ChatMessageRow

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


CHAT_ROLES = ("user", "assistant")


class ChatMessageRepository(ChatMessageRepositoryPort):
    """Append-only access to the ``chat_messages`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def append(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        model: str | None = None,
    ) -> int:
        if role not in CHAT_ROLES:
            raise ValueError(f"unknown chat role: {role!r}")
        if role == "user" and model is not None:
            raise ValueError("model must be None for user turns")
        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO chat_messages"
                " (session_id, role, content, model, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, model, created_at),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    def list_for_session(self, session_id: int) -> list[ChatMessageRow]:
        """Return every message for *session_id* in insertion order."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [_row_to_message(r) for r in rows]

    def list_for_session_paginated(
        self,
        session_id: int,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ChatMessageRow], int]:
        """Oldest-first page of messages plus total row count.

        Mirrors :meth:`ChatSessionRepository.list_for_project_paginated`:
        one ``COUNT(*)`` and one ``SELECT ... LIMIT ? OFFSET ?`` so the
        page does not load every row. Order is ``id ASC`` so the UI
        renders top-down chronologically.
        """
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._factory.connect() as conn:
            total_row = conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            total = int(total_row[0])
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ?"
                " ORDER BY id ASC LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            ).fetchall()
        return [_row_to_message(r) for r in rows], total

    def count_for_session(self, session_id: int) -> int:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row[0])

    def last_created_at(self, session_id: int) -> str | None:
        """Return the ``created_at`` of the most recent message, or None."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM chat_messages"
                " WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return row["created_at"] if row else None


def _row_to_message(row: Any) -> ChatMessageRow:
    return ChatMessageRow(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        model=row["model"],
        created_at=row["created_at"],
    )

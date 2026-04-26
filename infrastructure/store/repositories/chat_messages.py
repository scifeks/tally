"""ChatMessageRepository — manages the ``chat_messages`` table (Phase 8.1).

Each row is one turn within a chat session. ``role`` is ``user`` or
``assistant``; ``model`` is the LLM model identifier on assistant turns
and NULL on user turns. Messages are append-only in v1 — there is no
update or per-row delete API; deletion happens via cascade when the
parent session is deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


CHAT_ROLES = ("user", "assistant")


@dataclass(frozen=True)
class ChatMessageRow:
    id: int
    session_id: int
    role: str
    content: str
    model: str | None
    created_at: str


class ChatMessageRepository:
    """Append-only access to the ``chat_messages`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
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
            return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_for_session(self, session_id: int) -> list[ChatMessageRow]:
        """Return every message for *session_id* in insertion order."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [_row_to_message(r) for r in rows]

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

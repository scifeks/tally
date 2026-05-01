"""Domain entries for the chat surface.

``ChatSessionRow`` and ``ChatMessageRow`` are the row-shaped value objects
returned by the chat repository ports. They live in ``domain/`` so that
port signatures depend on domain types rather than infrastructure types
(Rule 7). The dataclasses are frozen and field-equivalent to the rows
persisted in ``chat_sessions`` and ``chat_messages``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatSessionRow:
    id: int
    project_id: int
    title: str
    created_at: str
    updated_at: str
    expired_at: str | None


@dataclass(frozen=True)
class ChatMessageRow:
    id: int
    session_id: int
    role: str
    content: str
    model: str | None
    created_at: str

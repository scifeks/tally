"""Domain entries for the chat surface.

``ChatSessionRow`` and ``ChatMessageRow`` are frozen row-shaped value
objects returned by chat repository ports. Frozen dataclasses preserve
immutability across adapter boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatSessionRow:
    id: int
    project_id: int
    title: str
    mode: str
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

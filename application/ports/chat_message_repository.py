"""Persistence port for the chat_messages table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.chat.entry import ChatMessageRow


class ChatMessageRepositoryPort(Protocol):
    def append(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        model: str | None = None,
    ) -> int: ...
    def list_for_session(self, session_id: int) -> list[ChatMessageRow]: ...
    def list_for_session_paginated(
        self,
        session_id: int,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ChatMessageRow], int]: ...
    def count_for_session(self, session_id: int) -> int: ...
    def last_created_at(self, session_id: int) -> str | None: ...

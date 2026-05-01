"""Persistence port for the ``chat_sessions`` table.

Concrete implementation lives at
``infrastructure.store.repositories.chat_sessions.ChatSessionRepository``.
Returned rows are domain types (`domain.chat.entry.ChatSessionRow`) so
the port boundary stays free of infrastructure dataclasses.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.chat.entry import ChatSessionRow


class ChatSessionRepositoryPort(Protocol):
    def create(self, *, project_id: int, title: str) -> int: ...
    def touch(self, session_id: int, when: str | None = None) -> None: ...
    def mark_expired(
        self,
        session_ids: Iterable[int],
        when: str | None = None,
    ) -> None: ...
    def delete(self, session_id: int) -> None: ...
    def get(self, session_id: int) -> ChatSessionRow | None: ...
    def list_for_project(
        self,
        project_id: int,
        *,
        include_expired: bool = True,
    ) -> list[ChatSessionRow]: ...
    def list_active_for_project(self, project_id: int) -> list[ChatSessionRow]: ...
    def list_for_project_paginated(
        self,
        project_id: int,
        *,
        offset: int,
        limit: int,
        include_expired: bool = True,
    ) -> tuple[list[ChatSessionRow], int]: ...
    def list_expired_for_project(self, project_id: int) -> list[ChatSessionRow]: ...
    def select_for_retention(
        self,
        project_id: int,
        *,
        keep: int,
    ) -> list[ChatSessionRow]: ...

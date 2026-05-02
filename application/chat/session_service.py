"""Application service for chat session and message CRUD.

Owns per-request construction of the chat persistence repos so route
modules do not import infrastructure persistence directly. Streaming
turn execution still lives in ``application.chat.service.stream_chat``;
the route hands it the repos exposed on this service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from application.chat.service import ChatSessionNotFound
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

if TYPE_CHECKING:
    from fastapi import Request

    from application.ports.chat_message_repository import ChatMessageRepositoryPort
    from application.ports.chat_session_repository import ChatSessionRepositoryPort
    from domain.chat.entry import ChatMessageRow, ChatSessionRow


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class ChatSessionService:
    """Chat session and message CRUD bound to a single project."""

    def __init__(
        self,
        session_repo: ChatSessionRepositoryPort,
        message_repo: ChatMessageRepositoryPort,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo

    @classmethod
    def from_request(cls, request: Request, project_id: int) -> Self:
        registry = request.app.state.project_registry
        row = registry.resolve_by_id(project_id)
        if row is None or row.get("archived_at"):
            raise ProjectNotFound(f"project {project_id} not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        return cls(
            session_repo=ChatSessionRepository(factory),
            message_repo=ChatMessageRepository(factory),
        )

    @property
    def session_repo(self) -> ChatSessionRepositoryPort:
        """Exposed for the streaming POST flow only."""
        return self._session_repo

    @property
    def message_repo(self) -> ChatMessageRepositoryPort:
        """Exposed for the streaming POST flow only."""
        return self._message_repo

    def create_session(self, *, project_id: int, title: str) -> ChatSessionRow:
        session_id = self._session_repo.create(project_id=project_id, title=title)
        row = self._session_repo.get(session_id)
        if row is None:
            raise ChatSessionNotFound(
                f"chat session {session_id} not found after creation"
            )
        return row

    def list_sessions(
        self,
        project_id: int,
        *,
        offset: int,
        limit: int,
        include_expired: bool = True,
    ) -> tuple[list[ChatSessionRow], int]:
        return self._session_repo.list_for_project_paginated(
            project_id,
            offset=offset,
            limit=limit,
            include_expired=include_expired,
        )

    def get_session_or_raise(
        self,
        session_id: int,
        project_id: int,
    ) -> ChatSessionRow:
        row = self._session_repo.get(session_id)
        if row is None or row.project_id != project_id:
            raise ChatSessionNotFound(f"chat session {session_id} not found")
        return row

    def delete_session(self, session_id: int, project_id: int) -> None:
        self.get_session_or_raise(session_id, project_id)
        self._session_repo.delete(session_id)

    def list_messages(
        self,
        session_id: int,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ChatMessageRow], int]:
        return self._message_repo.list_for_session_paginated(
            session_id,
            offset=offset,
            limit=limit,
        )

    def append_user_message(self, session_id: int, content: str) -> int:
        return self._message_repo.append(
            session_id=session_id,
            role="user",
            content=content,
        )

    def session_summary_metrics(self, session_id: int) -> tuple[str | None, int]:
        return (
            self._message_repo.last_created_at(session_id),
            self._message_repo.count_for_session(session_id),
        )

"""Application service for chat session and message CRUD plus stream
orchestration.

Owns per-request construction of the chat persistence repos so route
modules do not import infrastructure persistence directly. Stream
orchestration (validate, compose, persist user, spawn driver task,
register handle) and cancellation also live here so the web adapter is
free of ``asyncio.create_task`` / ``task.cancel()`` plumbing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from application.chat.run_registry import (
    ChatRunHandle,
    get_chat_run_registry,
)
from application.chat.service import (
    ChatRequest,
    ChatSessionExpired,
    ChatSessionNotFound,
    ChatStreamAlreadyRunning,
    ChatStreamNotRunning,
    ProjectNotFound,
    stream_chat,
)
from application.chat.stream_composer import ChatStreamComposer
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

if TYPE_CHECKING:
    from application.ports.chat_event_sink import ChatStreamSink
    from application.ports.chat_message_repository import ChatMessageRepositoryPort
    from application.ports.chat_session_repository import ChatSessionRepositoryPort
    from application.project.registry_service import ProjectRegistryService
    from application.rag.knowledge_base import FindingKnowledgeBase
    from domain.chat.entry import ChatMessageRow, ChatSessionRow


logger = logging.getLogger("application.chat.session_service")


@dataclass(frozen=True)
class SendMessageHandle:
    """Returned from :meth:`ChatSessionService.send_message`.

    The user row is already persisted; the assistant row will be
    written write-once on clean stream end and its id arrives on the
    SSE ``stream_end`` event.
    """

    user_message_id: int
    session_id: int
    project_id: int


class ChatSessionService:
    """Chat session and message CRUD plus stream orchestration."""

    def __init__(
        self,
        session_repo: ChatSessionRepositoryPort,
        message_repo: ChatMessageRepositoryPort,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo

    @classmethod
    def for_project(
        cls,
        registry: ProjectRegistryService,
        project_id: int,
    ) -> Self:
        row = registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
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
        return self._session_repo

    @property
    def message_repo(self) -> ChatMessageRepositoryPort:
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

    async def send_message(
        self,
        *,
        project_id: int,
        session_id: int,
        content: str,
        chat_sink: ChatStreamSink,
        project_registry: ProjectRegistryService,
        knowledge_base_cache: dict[str, FindingKnowledgeBase | None],
        base_path: str,
    ) -> SendMessageHandle:
        """Validate, compose, persist user, spawn driver, register handle.

        Raises:
            ChatSessionNotFound: session_id is unknown or wrong project.
            ChatSessionExpired: session has been sealed.
            ChatStreamAlreadyRunning: another stream is in flight for
                this session.
            RagUnavailable: per-project knowledge base cannot be built.
        """
        session = await asyncio.to_thread(
            self.get_session_or_raise, session_id, project_id
        )
        if session.expired_at is not None:
            raise ChatSessionExpired(
                f"chat session {session_id} is sealed (expired_at="
                f"{session.expired_at!r})"
            )

        registry = get_chat_run_registry()
        if registry.get(session_id) is not None:
            raise ChatStreamAlreadyRunning(
                f"chat stream for session {session_id} is already running"
            )

        composer = await asyncio.to_thread(
            ChatStreamComposer.for_project,
            project_registry,
            knowledge_base_cache,
            base_path,
            project_id,
        )

        user_message_id = await asyncio.to_thread(
            self.append_user_message, session_id, content
        )

        chat_request = ChatRequest(
            session_id=session_id,
            project_id=project_id,
            user_message=content,
        )
        task: asyncio.Task[None] = asyncio.create_task(
            self._drive_stream(
                chat_request=chat_request,
                composer=composer,
                chat_sink=chat_sink,
            ),
            name=f"chat-{session_id}",
        )
        registry.register(
            session_id=session_id,
            project_id=project_id,
            user_message_id=user_message_id,
            task=task,
        )
        return SendMessageHandle(
            user_message_id=user_message_id,
            session_id=session_id,
            project_id=project_id,
        )

    def cancel_stream(self, session_id: int, project_id: int) -> None:
        """Cancel the in-flight chat stream for *session_id*.

        Raises:
            ChatSessionNotFound: session_id is unknown or wrong project.
            ChatStreamNotRunning: no stream is currently in flight.
        """
        self.get_session_or_raise(session_id, project_id)
        handle = get_chat_run_registry().get(session_id)
        if handle is None:
            raise ChatStreamNotRunning(
                f"no chat stream is running for session {session_id}"
            )
        handle.task.cancel()

    def peek_active_stream(self, session_id: int) -> ChatRunHandle | None:
        """Return the registry handle for *session_id*, or None.

        Used by the SSE on-connect snapshot to expose the in-flight
        ``user_message_id`` without forcing the route to know the
        registry shape.
        """
        return get_chat_run_registry().get(session_id)

    async def _drive_stream(
        self,
        *,
        chat_request: ChatRequest,
        composer: ChatStreamComposer,
        chat_sink: ChatStreamSink,
    ) -> None:
        """Drive ``stream_chat`` to completion; unregister in finally.

        Tokens reach the SSE client via the sink; yielded chunks are
        discarded here. The finally always unregisters the handle, even
        on cancel or error, so a follow-up POST for the same session is
        not blocked.
        """
        try:
            gen = await stream_chat(
                chat_request,
                session_repo=self._session_repo,
                message_repo=self._message_repo,
                query_engine=composer.query_engine,
                provider=composer.provider,
                model_name=composer.model_name,
                event_sink=chat_sink,
            )
            try:
                async for _chunk in gen:
                    pass
            finally:
                await gen.aclose()  # type: ignore[union-attr]
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "chat stream failed for session %d", chat_request.session_id
            )
        finally:
            get_chat_run_registry().unregister(chat_request.session_id)

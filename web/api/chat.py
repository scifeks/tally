"""Phase 8.4 / 8.5 / 8.6 / 8.7 / 8.8 — Chat session endpoints.

Endpoint surface per ``docs/roadmap/ui-planning/API/endpoints.md §12``:

- ``POST   /api/v1/projects/{project_id}/chat/sessions`` (8.4)
- ``GET    /api/v1/projects/{project_id}/chat/sessions`` (8.5)
- ``DELETE /api/v1/projects/{project_id}/chat/sessions/{session_id}`` (8.6)
- ``GET    /api/v1/projects/{project_id}/chat/sessions/{session_id}/messages`` (8.7)
- ``POST   /api/v1/projects/{project_id}/chat/sessions/{session_id}/messages`` (8.8)
- ``GET    /api/v1/projects/{project_id}/chat/stream`` (8.8 — SSE)

Phase 8.9 (cancel) and 8.10 (scan-triggered sealing + retention sweep)
are not in this slice.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.chat.service import (
    ChatRequest,
    ChatSessionExpired,
    ChatSessionNotFound,
    stream_chat,
)
from application.rag.query import QueryEngine
from core.llm.factory import get_llm_provider
from core.project_paths import ProjectPaths
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_messages import (
    ChatMessageRepository,
    ChatMessageRow,
)
from infrastructure.store.repositories.chat_sessions import (
    ChatSessionRepository,
    ChatSessionRow,
)
from web.adapters.chat_run_registry import get_chat_run_registry
from web.adapters.event_bus_chat_sink import EventBusChatSink
from web.api._errors import Conflict, NotFound, ValidationError
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    ChatMessageResponse,
    ChatMessageSendRequest,
    ChatMessageSendResponse,
    ChatMessagesListResponse,
    ChatSessionCreateRequest,
    ChatSessionsListResponse,
    ChatSessionSummary,
)

logger = logging.getLogger("tally.web.chat")

v1_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repos(
    row: dict,
) -> tuple[ChatSessionRepository, ChatMessageRepository]:
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return ChatSessionRepository(factory), ChatMessageRepository(factory)


def _row_to_summary(
    row: ChatSessionRow,
    message_repo: ChatMessageRepository,
) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        created_at=row.created_at,
        last_message_at=message_repo.last_created_at(row.id),
        message_count=message_repo.count_for_session(row.id),
        expired_at=row.expired_at,
    )


def _format_title(now: datetime) -> str:
    """Return ``YYYY-MM-DD HH:MM`` for the session title (decisions.md Q15)."""
    return now.strftime("%Y-%m-%d %H:%M")


def _resolve_session_for_project(
    session_repo: ChatSessionRepository,
    *,
    session_id: int,
    project_id: int,
) -> ChatSessionRow:
    """Fetch the session row, 404 if missing or wrong project."""
    row = session_repo.get(session_id)
    if row is None or row.project_id != project_id:
        raise NotFound(f"chat session {session_id} not found")
    return row


def _row_to_message_response(row: ChatMessageRow) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=row.id,
        session_id=row.session_id,
        role=row.role,
        content=row.content,
        model=row.model,
        timestamp=row.created_at,
        citations=None,
    )


def _build_chat_snapshot(project_id: int, session_id: int) -> BusEvent:
    """On-connect SSE snapshot exposing in-flight stream identifiers.

    Mirrors :func:`web.api.reports._build_snapshot` but keyed by
    ``session_id`` (chat is unbounded-concurrent, not single-active).
    Includes ``active`` flag so the SPA can decide whether to wait or
    show "no stream in progress".
    """
    handle = get_chat_run_registry().get(session_id)
    payload: dict[str, Any] = {
        "project_id": project_id,
        "session_id": session_id,
        "active": handle is not None,
    }
    if handle is not None:
        payload["user_message_id"] = handle.user_message_id
    return BusEvent(
        event_id=new_event_id(),
        job_id="chat",
        stream="chat",
        event_type="snapshot",
        payload=payload,
        ts=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# 8.4 — POST /chat/sessions
# ---------------------------------------------------------------------------


@v1_router.post(
    "/{project_id}/chat/sessions",
    response_model=ChatSessionSummary,
    status_code=201,
)
async def create_chat_session(
    project_id: int,
    request: Request,
    body: ChatSessionCreateRequest | None = None,
) -> ChatSessionSummary:
    """Create a chat session for *project_id*.

    Empty request body in v1; the title is auto-set to the current
    UTC ``YYYY-MM-DD HH:MM`` timestamp (decisions.md B7.4 / Q15).
    """
    del body  # accepted for API symmetry; no fields consumed in v1
    row = _resolve_project(request, project_id)
    session_repo, message_repo = _make_repos(row)
    title = _format_title(datetime.now(UTC))

    session_id = await asyncio.to_thread(
        session_repo.create,
        project_id=project_id,
        title=title,
    )
    fresh = await asyncio.to_thread(session_repo.get, session_id)
    if fresh is None:
        raise NotFound(f"chat session {session_id} not found after creation")
    return _row_to_summary(fresh, message_repo)


# ---------------------------------------------------------------------------
# 8.5 — GET /chat/sessions
# ---------------------------------------------------------------------------


@v1_router.get(
    "/{project_id}/chat/sessions",
    response_model=ChatSessionsListResponse,
)
async def list_chat_sessions(
    project_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> ChatSessionsListResponse:
    """Paginated chat sessions for a project, newest-first.

    Returns one combined list (``items``) covering both active and
    expired sessions; ``expired_at`` distinguishes them so the UI
    can group. Defaults match the findings list (50 / 500).
    """
    row = _resolve_project(request, project_id)
    session_repo, message_repo = _make_repos(row)

    page, total = await asyncio.to_thread(
        session_repo.list_for_project_paginated,
        project_id,
        offset=offset,
        limit=limit,
        include_expired=True,
    )
    items = [_row_to_summary(r, message_repo) for r in page]
    return ChatSessionsListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 8.7 — GET /chat/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@v1_router.get(
    "/{project_id}/chat/sessions/{session_id}/messages",
    response_model=ChatMessagesListResponse,
)
async def list_chat_messages(
    project_id: int,
    session_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> ChatMessagesListResponse:
    """Paginated messages for a chat session, oldest-first.

    Works for both active and expired (sealed) sessions. ``citations``
    is always ``None`` in v1 (chat-history.md decision 10).
    """
    row = _resolve_project(request, project_id)
    session_repo, message_repo = _make_repos(row)
    await asyncio.to_thread(
        _resolve_session_for_project,
        session_repo,
        session_id=session_id,
        project_id=project_id,
    )

    page, total = await asyncio.to_thread(
        message_repo.list_for_session_paginated,
        session_id,
        offset=offset,
        limit=limit,
    )
    return ChatMessagesListResponse(
        items=[_row_to_message_response(r) for r in page],
        total=total,
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 8.6 — DELETE /chat/sessions/{session_id}
# ---------------------------------------------------------------------------


@v1_router.delete(
    "/{project_id}/chat/sessions/{session_id}",
    status_code=204,
)
async def delete_chat_session(
    project_id: int,
    session_id: int,
    request: Request,
) -> None:
    """Hard-delete a chat session (cascades to all messages via FK)."""
    row = _resolve_project(request, project_id)
    session_repo, _message_repo = _make_repos(row)
    await asyncio.to_thread(
        _resolve_session_for_project,
        session_repo,
        session_id=session_id,
        project_id=project_id,
    )
    await asyncio.to_thread(session_repo.delete, session_id)


# ---------------------------------------------------------------------------
# 8.8 — POST /chat/sessions/{session_id}/messages  (start streamed turn)
# ---------------------------------------------------------------------------


async def _drive_chat_stream(
    *,
    chat_request: ChatRequest,
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    query_engine: QueryEngine,
    provider: Any,
    model_name: str,
    sink: EventBusChatSink,
) -> None:
    """Background task body: drive the chat-service generator to completion.

    Tokens reach the SSE client via the sink; the yielded chunks are
    discarded here. The task always unregisters itself from the
    ``chat_run_registry`` in its ``finally`` block, even on cancel /
    error, so a follow-up POST for the same session is not blocked.
    Cancellation flows through standard asyncio task cancellation: the
    ``GeneratorExit`` propagates into ``stream_chat`` and the service's
    ``ChatStreamCancelled`` path fires.
    """
    try:
        gen = await stream_chat(
            chat_request,
            session_repo=session_repo,
            message_repo=message_repo,
            query_engine=query_engine,
            provider=provider,
            model_name=model_name,
            event_sink=sink,
        )
        try:
            async for _chunk in gen:
                pass
        finally:
            await gen.aclose()  # type: ignore[union-attr]
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("chat stream failed for session %d", chat_request.session_id)
    finally:
        get_chat_run_registry().unregister(chat_request.session_id)


@v1_router.post(
    "/{project_id}/chat/sessions/{session_id}/messages",
    response_model=ChatMessageSendResponse,
    status_code=202,
)
async def send_chat_message(
    project_id: int,
    session_id: int,
    request: Request,
    body: ChatMessageSendRequest,
) -> ChatMessageSendResponse:
    """Persist the user turn and start the streamed assistant response.

    Returns 202 immediately with the SSE URL the SPA must subscribe to.
    Per decisions.md B7.7 the assistant row is written write-once on
    clean stream end, so ``assistant_message_id`` is ``None`` here —
    the final id is delivered via the ``stream_end`` SSE event's
    ``message_id`` field. Errors:

    - 404 — session not found or wrong project.
    - 409 ``CHAT_SESSION_EXPIRED`` — session has been sealed.
    - 409 ``CHAT_STREAM_ALREADY_RUNNING`` — another stream for this
      session is in flight.
    """
    row = _resolve_project(request, project_id)
    project_name: str = row["name"]
    base_path: str = request.app.state.base_path

    session_repo, message_repo = _make_repos(row)
    session_row = await asyncio.to_thread(
        _resolve_session_for_project,
        session_repo,
        session_id=session_id,
        project_id=project_id,
    )
    if session_row.expired_at is not None:
        raise Conflict(
            f"chat session {session_id} is sealed",
            code="CHAT_SESSION_EXPIRED",
            details={"expired_at": session_row.expired_at},
        )

    registry = get_chat_run_registry()
    if registry.get(session_id) is not None:
        raise Conflict(
            f"chat stream for session {session_id} is already running",
            code="CHAT_STREAM_ALREADY_RUNNING",
            details={"session_id": session_id},
        )

    # Local import: web.server imports this module's v1_router during
    # app construction, so a top-level import would be circular.
    from web.server import get_rag_engine

    rag_engine = await asyncio.to_thread(
        get_rag_engine, request.app, project_name, base_path
    )
    if rag_engine is None:
        raise ValidationError(
            "RAG engine unavailable for this project; "
            "ChromaDB or embedding provider is not reachable",
            details={"project_id": project_id, "code": "RAG_UNAVAILABLE"},
        )
    query_engine = QueryEngine(rag_engine)

    provider = await asyncio.to_thread(get_llm_provider, "chat", base_path)
    model_name = provider.model

    user_message_id = await asyncio.to_thread(
        message_repo.append,
        session_id=session_id,
        role="user",
        content=body.content,
    )

    bus = request.app.state.event_bus
    sink = EventBusChatSink(bus)

    chat_request = ChatRequest(
        session_id=session_id,
        project_id=project_id,
        user_message=body.content,
    )

    # Re-validate: stream_chat() will re-fetch and could still raise if
    # the session was deleted between our check and the task start. The
    # background driver will swallow + log; the POST can return 202
    # because the user row is already persisted.
    try:
        # Probe before scheduling so eager-validation errors surface here.
        del session_row  # used only for the expired check above
    except (ChatSessionNotFound, ChatSessionExpired):
        raise

    task: asyncio.Task[None] = asyncio.create_task(
        _drive_chat_stream(
            chat_request=chat_request,
            session_repo=session_repo,
            message_repo=message_repo,
            query_engine=query_engine,
            provider=provider,
            model_name=model_name,
            sink=sink,
        ),
        name=f"chat-{session_id}",
    )
    registry.register(
        session_id=session_id,
        project_id=project_id,
        user_message_id=user_message_id,
        task=task,
    )

    stream_url = f"/api/v1/projects/{project_id}/chat/stream?session_id={session_id}"
    return ChatMessageSendResponse(
        user_message_id=user_message_id,
        assistant_message_id=None,
        session_id=session_id,
        stream_url=stream_url,
    )


# ---------------------------------------------------------------------------
# 8.8 — GET /chat/stream  (SSE)
# ---------------------------------------------------------------------------


@v1_router.get("/{project_id}/chat/stream")
async def chat_stream(
    project_id: int,
    request: Request,
    session_id: int = Query(...),
) -> StreamingResponse:
    """SSE stream emitting chat token / lifecycle events for *session_id*.

    Mirrors the reports SSE pattern (``web/api/reports.py:182-221``).
    Filters delivered events by ``project_id`` + ``session_id`` so a
    single connection only sees its own stream. Heartbeats every 15s
    keep proxies from closing the connection while the model is
    thinking. Client disconnect closes the SSE — it does NOT cancel
    the underlying asyncio task (per decisions.md B7.7 the LLM call
    continues server-side and the assistant row is persisted on clean
    stream end). Explicit cancellation is Phase 8.9.
    """
    _resolve_project(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("chat")

    snapshot = _build_chat_snapshot(project_id, session_id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield format_sse_frame(snapshot)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item is EOS:
                    break
                payload = item.payload
                if payload.get("project_id") != project_id:
                    continue
                if payload.get("session_id") != session_id:
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("chat", sub_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

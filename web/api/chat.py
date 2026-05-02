"""Chat session endpoints.

Endpoint surface:

- ``POST   /api/v1/projects/{project_id}/chat/sessions``
- ``GET    /api/v1/projects/{project_id}/chat/sessions``
- ``DELETE /api/v1/projects/{project_id}/chat/sessions/{session_id}``
- ``GET    /api/v1/projects/{project_id}/chat/sessions/{session_id}/messages``
- ``POST   /api/v1/projects/{project_id}/chat/sessions/{session_id}/messages``
- ``GET    /api/v1/projects/{project_id}/chat/stream`` (SSE)
- ``POST   /api/v1/projects/{project_id}/chat/sessions/{session_id}/cancel``

Routes resolve a ``ChatSessionService`` per request and call the service for
all persistence work; infrastructure repositories are not imported here.
The streaming POST passes the service's repo handles into ``stream_chat``
so the in-flight assistant turn shares the per-request connection factory.
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
from application.chat.session_service import ChatSessionService, ProjectNotFound
from application.chat.stream_composer import ChatStreamComposer, RagUnavailable
from domain.chat.entry import ChatMessageRow, ChatSessionRow
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from web.adapters.chat_run_registry import get_chat_run_registry
from web.adapters.event_bus_chat_sink import EventBusChatSink
from web.api._errors import Conflict, NotFound, ValidationError
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    ChatMessageCancelResponse,
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


def _service(request: Request, project_id: int) -> ChatSessionService:
    """Build a ChatSessionService for *project_id* or raise 404."""
    try:
        return ChatSessionService.from_request(request, project_id)
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _row_to_summary(
    row: ChatSessionRow,
    service: ChatSessionService,
) -> ChatSessionSummary:
    last_at, count = service.session_summary_metrics(row.id)
    return ChatSessionSummary(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        created_at=row.created_at,
        last_message_at=last_at,
        message_count=count,
        expired_at=row.expired_at,
    )


def _format_title(now: datetime) -> str:
    """Render the session auto-title as ``YYYY-MM-DD HH:MM``."""
    return now.strftime("%Y-%m-%d %H:%M")


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

    Includes ``active`` so the SPA can decide whether to wait for tokens
    or render the empty state.
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
    UTC ``YYYY-MM-DD HH:MM`` timestamp.
    """
    del body  # accepted for API symmetry; no fields consumed in v1
    service = _service(request, project_id)
    title = _format_title(datetime.now(UTC))
    try:
        row = await asyncio.to_thread(
            service.create_session,
            project_id=project_id,
            title=title,
        )
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc
    return _row_to_summary(row, service)


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
    expired sessions; ``expired_at`` distinguishes them so the UI can
    group. Defaults match the findings list (50 / 500).
    """
    service = _service(request, project_id)
    page, total = await asyncio.to_thread(
        service.list_sessions,
        project_id,
        offset=offset,
        limit=limit,
        include_expired=True,
    )
    items = [_row_to_summary(r, service) for r in page]
    return ChatSessionsListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


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
    is always ``None`` in v1.
    """
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.get_session_or_raise, session_id, project_id)
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc

    page, total = await asyncio.to_thread(
        service.list_messages,
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
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.delete_session, session_id, project_id)
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc


async def _drive_chat_stream(
    *,
    chat_request: ChatRequest,
    session_repo: Any,
    message_repo: Any,
    query_engine: Any,
    provider: Any,
    model_name: str,
    sink: EventBusChatSink,
) -> None:
    """Background task body: drive the chat-service generator to completion.

    Tokens reach the SSE client via the sink; yielded chunks are
    discarded here. The task always unregisters itself from the
    chat run registry in its ``finally`` block, even on cancel or
    error, so a follow-up POST for the same session is not blocked.
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
    The assistant row is written write-once on clean stream end, so
    ``assistant_message_id`` is ``None`` here; the final id arrives on
    the ``stream_end`` SSE event's ``message_id`` field. Errors:

    - 404: session not found or wrong project.
    - 409 ``CHAT_SESSION_EXPIRED``: session has been sealed.
    - 409 ``CHAT_STREAM_ALREADY_RUNNING``: another stream for this
      session is in flight.
    """
    _resolve_project(request, project_id)

    service = _service(request, project_id)
    try:
        session_row = await asyncio.to_thread(
            service.get_session_or_raise, session_id, project_id
        )
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc
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

    try:
        composer = await asyncio.to_thread(
            ChatStreamComposer.from_request, request, project_id
        )
    except RagUnavailable as exc:
        raise ValidationError(
            str(exc),
            details={"project_id": project_id, "code": "RAG_UNAVAILABLE"},
        ) from exc

    user_message_id = await asyncio.to_thread(
        service.append_user_message, session_id, body.content
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
    # background driver swallows + logs; the POST returns 202 because
    # the user row is already persisted.
    try:
        del session_row  # used only for the expired check above
    except (ChatSessionNotFound, ChatSessionExpired):
        raise

    task: asyncio.Task[None] = asyncio.create_task(
        _drive_chat_stream(
            chat_request=chat_request,
            session_repo=service.session_repo,
            message_repo=service.message_repo,
            query_engine=composer.query_engine,
            provider=composer.provider,
            model_name=composer.model_name,
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


@v1_router.post(
    "/{project_id}/chat/sessions/{session_id}/cancel",
    response_model=ChatMessageCancelResponse,
    status_code=202,
)
async def cancel_chat_stream(
    project_id: int,
    session_id: int,
    request: Request,
) -> ChatMessageCancelResponse:
    """Cancel the in-flight assistant stream for *session_id*.

    Looks up the asyncio task in the chat run registry and calls
    ``task.cancel()``. The chat-service generator's ``GeneratorExit``
    path emits ``ChatStreamCancelled`` (projected to SSE as
    ``stream_cancelled``) and does not persist the assistant turn. The
    driver's ``finally`` unregisters the handle so a follow-up POST is
    not blocked. Errors:

    - 404: session not found or wrong project.
    - 409 ``CHAT_NO_ACTIVE_STREAM``: no stream is currently in flight
      for *session_id*.

    ``cancelled_message_id`` is ``None`` in v1: the assistant id is
    only assigned at ``stream_end``, after which there is nothing left
    to cancel.
    """
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.get_session_or_raise, session_id, project_id)
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc

    handle = get_chat_run_registry().get(session_id)
    if handle is None:
        raise Conflict(
            f"no chat stream is running for session {session_id}",
            code="CHAT_NO_ACTIVE_STREAM",
            details={"session_id": session_id},
        )
    handle.task.cancel()
    return ChatMessageCancelResponse(
        session_id=session_id,
        cancelled_message_id=None,
    )


@v1_router.get("/{project_id}/chat/stream")
async def chat_stream(
    project_id: int,
    request: Request,
    session_id: int = Query(...),
) -> StreamingResponse:
    """SSE stream emitting chat token / lifecycle events for *session_id*.

    Filters delivered events by ``project_id`` + ``session_id`` so a
    single connection only sees its own stream. Heartbeats every 15s
    keep proxies from closing the connection while the model is
    thinking. Client disconnect closes the SSE; it does not cancel the
    underlying asyncio task. Explicit cancellation is the cancel route.
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

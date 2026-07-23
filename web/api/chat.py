"""Chat session endpoints."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.chat.service import (
    ChatSessionExpired,
    ChatSessionNotFound,
    ChatStreamAlreadyRunning,
    ChatStreamNotRunning,
)
from application.chat.session_service import ChatSessionService
from application.chat.stream_composer import RagUnavailable
from application.events.ids import new_event_id
from application.events.types import EOS, BusEvent
from domain.chat.entry import ChatMessageRow, ChatSessionRow
from factories.persistence import (
    ProjectNotFound,
    create_chat_session_service,
)
from web.adapters.event_bus_chat_sink import EventBusChatSink
from web.api._errors import Conflict, NotFound, ValidationError
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
from web.sse import format_sse_frame

logger = logging.getLogger("tally.web.chat")

v1_router = APIRouter()


def _service(request: Request, project_id: int) -> ChatSessionService:
    """Resolve the service for project_id, raising 404 if not found."""
    try:
        return create_chat_session_service(
            request.app.state.project_registry, project_id
        )
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
    """Format timestamp as session title."""
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


def _build_chat_snapshot(
    service: ChatSessionService,
    project_id: int,
    session_id: int,
) -> BusEvent:
    """Build SSE snapshot with stream state for client reconnect."""
    handle = service.peek_active_stream(session_id)
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
    """Create a chat session with auto-generated title."""
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
    """List active and expired sessions, newest first."""
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
    """List messages for a session, oldest first."""
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
    """Delete a chat session and cascade delete all messages."""
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.delete_session, session_id, project_id)
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc


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
    """Queue user message and start streamed assistant response."""
    service = _service(request, project_id)
    sink = EventBusChatSink(request.app.state.event_bus)
    try:
        result = await service.send_message(
            project_id=project_id,
            session_id=session_id,
            content=body.content,
            chat_sink=sink,
            project_registry=request.app.state.project_registry,
            knowledge_base_cache=request.app.state.knowledge_base_cache,
            base_path=request.app.state.base_path,
            document_store_cache=request.app.state.document_store_cache,
        )
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc
    except ChatSessionExpired as exc:
        raise Conflict(
            str(exc),
            code="CHAT_SESSION_EXPIRED",
            details={"session_id": session_id},
        ) from exc
    except ChatStreamAlreadyRunning as exc:
        raise Conflict(
            str(exc),
            code="CHAT_STREAM_ALREADY_RUNNING",
            details={"session_id": session_id},
        ) from exc
    except RagUnavailable as exc:
        raise ValidationError(
            str(exc),
            details={"project_id": project_id, "code": "RAG_UNAVAILABLE"},
        ) from exc

    stream_url = f"/api/v1/projects/{project_id}/chat/stream?session_id={session_id}"
    return ChatMessageSendResponse(
        user_message_id=result.user_message_id,
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
    """Cancel in-flight assistant stream for a session."""
    service = _service(request, project_id)
    try:
        service.cancel_stream(session_id, project_id)
    except ChatSessionNotFound as exc:
        raise NotFound(str(exc)) from exc
    except ChatStreamNotRunning as exc:
        raise Conflict(
            str(exc),
            code="CHAT_NO_ACTIVE_STREAM",
            details={"session_id": session_id},
        ) from exc
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
    """Stream chat tokens and lifecycle events for a session."""
    service = _service(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("chat")

    snapshot = _build_chat_snapshot(service, project_id, session_id)

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

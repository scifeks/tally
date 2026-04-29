"""Web adapter: project ChatEvents onto the async EventBus (Phase 8.8).

The chat application service emits domain ``ChatEvent``s through the
``ChatStreamSink`` port (sync ``emit``). This adapter projects each
event into a :class:`BusEvent` on the process-singleton :class:`EventBus`
under ``stream="chat"`` so the SSE endpoint can fan it out to the SPA.

Unlike the report / scan / triage runners (which are daemon threads),
``application.chat.service.stream_chat`` is an async generator running
on the FastAPI event loop. ``EventBus.publish_threadsafe`` is implemented
via :func:`asyncio.run_coroutine_threadsafe`, which is safe from the
same loop, so the sink can stay sync to match the Phase 8.2 port. The
bus publish failure is swallowed (``contextlib.suppress``) so chat
streaming never fails because nothing is listening.

Field projection mirrors ``endpoints.md §15.4`` with two deliberate
remaps: ``assistant_message_id -> message_id`` for the public payload
shape, and ``ChatToken.token -> chunk`` so the wire payload does not
collide with the ``token`` key in
``infrastructure.security.redaction.SENSITIVE_KEYS`` (which would
otherwise replace each LLM chunk with ``***REDACTED***`` at
``format_sse_frame``). ``ChatStreamCompleted.content`` projects
through unchanged.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from domain.pipeline.chat_events import (
    ChatEvent,
    ChatStreamCancelled,
    ChatStreamCompleted,
    ChatStreamFailed,
    ChatToken,
    event_type_name,
)
from infrastructure.events.bus import EventBus
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import BusEvent

CHAT_JOB_ID = "chat"
CHAT_STREAM = "chat"


def _payload_for(event: ChatEvent) -> dict[str, Any]:
    """Project a ChatEvent into the §15.4 SSE payload mapping.

    Common fields: ``session_id``, ``project_id`` (kept for SSE filter),
    ``message_id`` (= ``assistant_message_id`` — populated only on
    ``stream_end``), ``user_message_id`` (kept for snapshot use).
    Per-type extras: ``chunk`` (token chunk text), ``content`` (full
    assistant turn), ``error`` + ``message`` (failure / cancellation
    detail).
    """
    base: dict[str, Any] = {
        "session_id": event.session_id,
        "project_id": event.project_id,
        "message_id": event.assistant_message_id,
        "user_message_id": event.user_message_id,
    }
    if isinstance(event, ChatToken):
        base["chunk"] = event.token
    elif isinstance(event, ChatStreamCompleted):
        base["content"] = event.content
    elif isinstance(event, ChatStreamFailed):
        base["error"] = event.error
        base["message"] = event.message
    elif isinstance(event, ChatStreamCancelled):
        base["message"] = event.message
    return base


class EventBusChatSink:
    """Publish chat events to a process-singleton EventBus."""

    def __init__(self, bus: EventBus, *, job_id: str = CHAT_JOB_ID) -> None:
        self._bus = bus
        self._job_id = job_id

    def emit(self, event: ChatEvent) -> None:
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=CHAT_STREAM,
            event_type=event_type_name(event),
            payload=_payload_for(event),
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._bus.publish_threadsafe(bus_event)

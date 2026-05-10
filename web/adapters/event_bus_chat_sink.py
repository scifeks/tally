"""Web adapter: project ChatEvents onto the async EventBus.

The chat application service emits domain ``ChatEvent``s through the
``ChatStreamSink`` port. This adapter projects each event into a
:class:`BusEvent` on the process-singleton :class:`EventBus` under
``stream="chat"`` so the SSE endpoint can fan it out to the SPA.
Two deliberate field remaps occur: ``assistant_message_id`` to
``message_id`` for the public payload shape, and ``ChatToken.token``
to ``chunk`` to avoid collision with the ``token`` key in sensitive
keys.
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
    """Project a ChatEvent into an SSE payload mapping.

    Common fields: ``session_id``, ``project_id``, ``message_id``
    (from ``assistant_message_id``), ``user_message_id``. Per-type
    extras: ``chunk``, ``content``, ``error``, ``message``.
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

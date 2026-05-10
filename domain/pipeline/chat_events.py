"""Chat lifecycle events.

Domain-pure events (no transport concerns). The ``ChatStreamSink`` port
projects them into either a REPL discard or an async ``BusEvent`` for
SSE fan-out. A chat stream is identified by ``session_id`` (the primary
key of the ``chat_sessions`` row).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def _new_event_id() -> str:
    return str(uuid4())


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class _ChatEventBase:
    session_id: int
    project_id: int
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    id: str = field(default_factory=_new_event_id)
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class ChatStreamStarted(_ChatEventBase):
    message: str = ""


@dataclass(frozen=True)
class ChatToken(_ChatEventBase):
    token: str = ""


@dataclass(frozen=True)
class ChatStreamCompleted(_ChatEventBase):
    content: str = ""


@dataclass(frozen=True)
class ChatStreamFailed(_ChatEventBase):
    error: str = ""
    message: str = ""


@dataclass(frozen=True)
class ChatStreamCancelled(_ChatEventBase):
    message: str = ""


type ChatEvent = (
    ChatStreamStarted
    | ChatToken
    | ChatStreamCompleted
    | ChatStreamFailed
    | ChatStreamCancelled
)


_EVENT_TYPE_NAMES: dict[type, str] = {
    ChatStreamStarted: "stream_start",
    ChatToken: "token",
    ChatStreamCompleted: "stream_end",
    ChatStreamFailed: "error",
    ChatStreamCancelled: "stream_cancelled",
}


def event_type_name(event: ChatEvent) -> str:
    """Return the SSE event_type string for *event*."""
    return _EVENT_TYPE_NAMES[type(event)]

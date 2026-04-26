"""ChatStreamSink port — destination for chat lifecycle events (Phase 8.2).

The chat application service calls ``sink.emit(event)`` on every state
transition (stream start, per-token, stream end / cancelled / failed).
Concrete adapters decide what to do with the event:

- Tests / REPL parity: ``NullChatStreamSink`` discards every event.
- API adapter (Phase 8.8): ``EventBusChatSink`` projects each event into
  a ``BusEvent(stream="chat", ...)`` and publishes it on the
  process-singleton ``EventBus`` for SSE fan-out.

The Phase 8.2 service is HTTP/SSE-agnostic; the sink is the only seam
between the core and the eventual web adapter.
"""

from __future__ import annotations

from typing import Protocol

from domain.pipeline.chat_events import ChatEvent


class ChatStreamSink(Protocol):
    """Sink for domain-pure chat lifecycle events."""

    def emit(self, event: ChatEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullChatStreamSink:
    """Discards every event. Default for tests and the no-op REPL parity path."""

    def emit(self, event: ChatEvent) -> None:
        del event
        return None

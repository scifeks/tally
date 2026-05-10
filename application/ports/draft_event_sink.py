"""Destination for draft lifecycle events.

The draft orchestrator calls ``sink.emit(event)`` on every state transition.
Concrete adapters decide what to do with the event:

- REPL adapter (``ConsoleDraftEventSink``): prints cosmetic progress to the
  Rich console.
- API adapter (``EventBusDraftSink``): projects the event into a
  ``BusEvent(stream="report_draft", ...)`` and publishes it to the
  process-singleton ``EventBus`` for SSE fan-out.
"""

from __future__ import annotations

from typing import Protocol

from domain.pipeline.report_events import DraftEvent


class DraftEventSink(Protocol):
    """Sink for domain-pure draft lifecycle events."""

    def emit(self, event: DraftEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullDraftEventSink:
    """Discards every event. Default for tests and the REPL parity path."""

    def emit(self, event: DraftEvent) -> None:
        del event
        return None

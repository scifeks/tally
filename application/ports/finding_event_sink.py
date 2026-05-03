"""Destination for finding lifecycle events.

The findings service calls ``sink.emit(event)`` after a successful
analyst PATCH. Concrete adapters decide what to do with the event:

- API adapter (``EventBusFindingSink``): projects the event into a
  ``BusEvent(stream="finding", ...)`` and publishes it to the
  process-singleton ``EventBus`` for SSE fan-out.
- REPL adapter / tests: ``NullFindingEventSink`` swallows every event.
"""

from __future__ import annotations

from typing import Protocol

from domain.findings.events import FindingUpdated


class FindingEventSink(Protocol):
    """Sink for domain-pure finding lifecycle events."""

    def emit(self, event: FindingUpdated) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullFindingEventSink:
    """Discards every event. Default for tests and REPL parity paths."""

    def emit(self, event: FindingUpdated) -> None:
        del event
        return None

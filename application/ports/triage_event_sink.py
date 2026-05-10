"""Destination for triage lifecycle events.

The triage runner calls ``sink.emit(event)`` on every state transition.
Concrete adapters decide what to do with the event:

- REPL adapter (``ConsoleTriageEventSink``): no-op. The REPL's existing
  ``print()`` / logging output remains in place to preserve byte-identical
  REPL behavior.
- API adapter (``EventBusTriageSink``): projects the event into a
  ``BusEvent(stream="triage", ...)`` and publishes it to the
  process-singleton ``EventBus`` for SSE fan-out.
"""

from __future__ import annotations

from typing import Protocol

from domain.pipeline.triage_events import TriageEvent


class TriageEventSink(Protocol):
    """Sink for domain-pure triage lifecycle events."""

    def emit(self, event: TriageEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullTriageEventSink:
    """Discards every event. Default for tests and the REPL parity path."""

    def emit(self, event: TriageEvent) -> None:
        del event
        return None

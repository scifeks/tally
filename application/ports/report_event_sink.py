"""Destination for report lifecycle events.

The report runner calls ``sink.emit(event)`` on every state transition.
Concrete adapters decide what to do with the event:

- REPL adapter: defaults to ``NullReportEventSink``. The REPL's existing
  ``console.print()`` output remains in place to preserve byte-identical
  REPL behavior.
- API adapter (``EventBusReportSink``): projects the event into a
  ``BusEvent(stream="report", ...)`` and publishes it to the
  process-singleton ``EventBus`` for SSE fan-out.
"""

from __future__ import annotations

from typing import Protocol

from domain.pipeline.report_events import ReportEvent


class ReportEventSink(Protocol):
    """Sink for domain-pure report lifecycle events."""

    def emit(self, event: ReportEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullReportEventSink:
    """Discards every event. Default for tests and the REPL parity path."""

    def emit(self, event: ReportEvent) -> None:
        del event
        return None

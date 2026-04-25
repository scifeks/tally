"""ScanEventSink port — destination for scan lifecycle events (Phase 5.2).

The orchestrator and scan-types layer call ``sink.emit(event)`` on every
state transition. Concrete adapters decide what to do with the event:

- REPL adapter (``ConsoleScanEventSink``): no-op. Visual REPL output
  comes from the existing ``OrchestratorDisplay`` calls, which remain in
  place to preserve byte-identical REPL behavior.
- API adapter (``EventBusScanSink``): projects the event into a
  ``BusEvent(stream="scan", ...)`` and publishes it to the
  process-singleton ``EventBus`` for SSE fan-out.
"""

from __future__ import annotations

from typing import Protocol

from domain.pipeline.scan_events import ScanEvent


class ScanEventSink(Protocol):
    """Sink for domain-pure scan lifecycle events."""

    def emit(self, event: ScanEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullScanEventSink:
    """Discards every event. Default for tests and the REPL parity path."""

    def emit(self, event: ScanEvent) -> None:  # noqa: D401
        del event
        return None

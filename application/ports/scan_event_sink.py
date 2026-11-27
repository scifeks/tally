"""Destination for scan lifecycle events.

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

import logging
from collections.abc import Sequence
from typing import Protocol

from domain.pipeline.scan_events import ScanEvent

logger = logging.getLogger(__name__)


class ScanEventSink(Protocol):
    """Sink for domain-pure scan lifecycle events."""

    def emit(self, event: ScanEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullScanEventSink:
    """Discards every event. Default for tests and the REPL parity path."""

    def emit(self, event: ScanEvent) -> None:
        del event
        return None


class FanOutScanEventSink:
    """Forwards each event to several sinks, isolating their failures."""

    def __init__(self, sinks: Sequence[ScanEventSink]) -> None:
        self._sinks = tuple(sinks)

    def emit(self, event: ScanEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:
                logger.exception("scan event sink %s raised", type(sink).__name__)

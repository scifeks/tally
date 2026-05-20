"""Destination for report metadata update events."""

from __future__ import annotations

from typing import Protocol

from domain.reports.events import ReportUpdateEvent


class ReportUpdateEventSink(Protocol):
    """Sink for domain-pure report update events."""

    def emit(self, event: ReportUpdateEvent) -> None:
        """Receive *event*. Implementations must not raise on transport errors."""
        ...


class NullReportUpdateEventSink:
    """Discards every event. Default for tests and REPL parity paths."""

    def emit(self, event: ReportUpdateEvent) -> None:
        del event
        return None

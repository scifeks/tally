"""Destination for finding lifecycle events."""

from __future__ import annotations

from typing import Protocol

from domain.findings.events import (
    FindingCreated,
    FindingDeleted,
    FindingUpdated,
)

FindingEvent = FindingCreated | FindingUpdated | FindingDeleted


class FindingEventSink(Protocol):
    """Sink for domain-pure finding lifecycle events."""

    def emit(self, event: FindingEvent) -> None: ...


class NullFindingEventSink:
    """Discards every event."""

    def emit(self, event: FindingEvent) -> None:
        del event
        return None

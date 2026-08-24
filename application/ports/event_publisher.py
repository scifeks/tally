from __future__ import annotations

from typing import Protocol

from domain.pipeline.bus_event import BusEvent


class EventPublisherPort(Protocol):
    def publish_threadsafe(self, event: BusEvent) -> None: ...

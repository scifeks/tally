from __future__ import annotations

from threading import Lock

from infrastructure.events.bus import EventBus
from infrastructure.events.exceptions import (
    BusError,
    SubscriberClosed,
    UnknownJob,
)
from infrastructure.events.types import EOS, BusEvent, SubscriberId

_bus: EventBus | None = None
_bus_lock = Lock()


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_bus() -> None:
    global _bus
    with _bus_lock:
        _bus = None


__all__ = [
    "EventBus",
    "get_bus",
    "reset_bus",
    "BusError",
    "SubscriberClosed",
    "UnknownJob",
    "BusEvent",
    "EOS",
    "SubscriberId",
]

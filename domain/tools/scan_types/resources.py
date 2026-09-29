"""Pure-domain Protocol for execution resources consumed by ScanType strategies."""

from __future__ import annotations

from typing import Any, Protocol


class IExecutionResources(Protocol):
    executor: Any
    registry: Any
    factory: Any
    event_bus: Any
    display: Any
    event_sink: Any
    http_runner: Any

"""Event types and synchronous EventBus for the tally pipeline."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.tools.base import ToolResult


@dataclass
class ToolCompleted:
    result: ToolResult
    profile: str
    run_id: int | None
    project_name: str
    base_path: str


@dataclass
class IngestCompleted:
    doc_ids: list[str]
    failed_tools: list[str]
    run_id: int | None
    project_name: str
    base_path: str


@dataclass
class EnrichmentCompleted:
    doc_ids: list[str]
    partial_success: bool
    run_id: int | None
    project_name: str
    base_path: str


class EventBus:
    """Synchronous observer bus.

    Handlers execute in the dispatcher's call stack, in registration order.
    Multiple subscribers per event type are supported.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        """Register *handler* to be called whenever *event_type* is dispatched."""
        self._handlers[event_type].append(handler)

    def dispatch(self, event: object) -> None:
        """Call all handlers registered for ``type(event)``."""
        for handler in self._handlers[type(event)]:
            handler(event)

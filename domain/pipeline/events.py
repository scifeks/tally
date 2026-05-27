"""Event types and synchronous EventBus for the tally pipeline."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from domain.tools.base import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ToolCompleted:
    result: ToolResult
    profile: str
    run_id: int | None
    project_name: str
    base_path: str
    repo: str | None = None


@dataclass
class IngestCompleted:
    ids: list[int]
    failed_tools: list[str]
    run_id: int | None
    project_name: str
    base_path: str


@dataclass
class EnrichmentCompleted:
    ids: list[int]
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
        self._cleanup_targets: list[Any] = []

    def subscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        """Register *handler* to be called whenever *event_type* is dispatched."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        """Remove a previously registered handler."""
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def register_cleanup_target(self, target: Any) -> None:
        """Register an object with a close() method for cleanup after use."""
        self._cleanup_targets.append(target)

    def dispatch(self, event: object) -> None:
        """Call all handlers registered for ``type(event)``."""
        for handler in self._handlers[type(event)]:
            handler(event)

    def cleanup(self) -> None:
        """Close all registered cleanup targets."""
        for target in self._cleanup_targets:
            try:
                if hasattr(target, "close") and callable(target.close):
                    target.close()
            except Exception:
                logger.exception(
                    "cleanup failed for %s",
                    type(target).__name__,
                )

"""ExecutionResources: bundles application-layer services for scan type strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.tools.executor import ToolExecutor
    from application.tools.factory import ToolWrapperFactory
    from application.tools.registry import ToolRegistry
    from domain.pipeline.events import EventBus
    from domain.tools.display import DisplayProtocol


@dataclass
class ExecutionResources:
    executor: ToolExecutor
    registry: ToolRegistry
    factory: ToolWrapperFactory
    event_bus: EventBus
    display: DisplayProtocol

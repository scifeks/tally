"""ExecutionResources: bundles application-layer services for scan type strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.tools.executor import ToolExecutor
    from application.tools.factory import ToolWrapperFactory
    from application.tools.registry import ToolRegistry


@dataclass
class ExecutionResources:
    executor: ToolExecutor
    registry: ToolRegistry
    factory: ToolWrapperFactory

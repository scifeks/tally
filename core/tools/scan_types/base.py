"""Abstract base class and execution resources for scan types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.tools.executor import ToolExecutor
from core.tools.factory import ToolWrapperFactory
from core.tools.registry import ToolRegistry
from core.tools.scan_types.models import ScanSummary, ScanTypeConfig


@dataclass
class ExecutionResources:
    executor: ToolExecutor
    registry: ToolRegistry
    factory: ToolWrapperFactory


class ScanType(ABC):
    @abstractmethod
    def execute(
        self, config: ScanTypeConfig, resources: ExecutionResources
    ) -> ScanSummary: ...

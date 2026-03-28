"""Abstract base class for scan type strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from domain.tools.scan_types.resources import IExecutionResources

if TYPE_CHECKING:
    from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig


class ScanType(ABC):
    @abstractmethod
    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary: ...

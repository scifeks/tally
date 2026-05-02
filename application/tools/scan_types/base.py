"""Abstract base class for scan type strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod

from application.tools.scan_types.models import ScanTypeConfig
from domain.tools.scan_types.models import ScanSummary
from domain.tools.scan_types.resources import IExecutionResources


class ScanType(ABC):
    @abstractmethod
    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary: ...

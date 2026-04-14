"""SegmentScan — validates a segment name and delegates to the right scan type."""

from __future__ import annotations

from typing import Any, cast

from application.tools.registry import ToolRegistry
from application.tools.scan_types.execution import tools_for_segment
from application.tools.scan_types.repo_segment import RepoSegmentScan
from domain.tools.exceptions import InvalidSegmentError
from domain.tools.scan_types.base import ScanType
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig
from domain.tools.scan_types.resources import IExecutionResources


class SegmentScan(ScanType):
    """Validate a segment name and delegate to the appropriate scan type."""

    def __init__(self, segment_name: str) -> None:
        self.segment_name = segment_name

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        registry = cast(ToolRegistry, resources.registry)
        _all_tools: list[Any] = registry.get_all_tools()
        valid_segments = {t.scan_segment for t in _all_tools}
        if self.segment_name not in valid_segments:
            raise InvalidSegmentError(self.segment_name, sorted(valid_segments))
        return RepoSegmentScan(
            tools_for_segment(self.segment_name, registry),
            segment_name=self.segment_name,
        ).execute(config, resources)

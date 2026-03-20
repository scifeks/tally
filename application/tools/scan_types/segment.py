"""SegmentScan — validates a segment name and delegates to the right scan type."""

from __future__ import annotations

from typing import Any

from application.tools.scan_types._helpers import _tools_for_segment
from application.tools.scan_types.network_segment import NetworkSegmentScan
from application.tools.scan_types.repo_segment import RepoSegmentScan
from application.tools.scan_types.resources import ExecutionResources
from domain.tools.exceptions import InvalidSegmentError
from domain.tools.scan_types.base import ScanType
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig


class SegmentScan(ScanType):
    """Validate a segment name and delegate to the appropriate scan type."""

    def __init__(self, segment_name: str) -> None:
        self.segment_name = segment_name

    def execute(
        self, config: ScanTypeConfig, resources: ExecutionResources
    ) -> ScanSummary:
        _all_tools: list[Any] = resources.registry.get_all_tools()
        valid_segments = {t.scan_segment for t in _all_tools}
        if self.segment_name not in valid_segments:
            raise InvalidSegmentError(self.segment_name, sorted(valid_segments))
        if self.segment_name == "network":
            return NetworkSegmentScan().execute(config, resources)
        return RepoSegmentScan(
            _tools_for_segment(self.segment_name, resources.registry)
        ).execute(config, resources)

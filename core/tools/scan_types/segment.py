"""SegmentScan — validates a segment name and delegates to the right scan type."""

from __future__ import annotations

from typing import Any

from core.tools.exceptions import InvalidSegmentError
from core.tools.scan_types.base import ScanType, _tools_for_segment
from core.tools.scan_types.models import ScanSummary, ScanTypeConfig
from core.tools.scan_types.network_segment import NetworkSegmentScan
from core.tools.scan_types.repo_segment import RepoSegmentScan


class SegmentScan(ScanType):
    """Validate a segment name and delegate to the appropriate scan type."""

    def __init__(self, segment_name: str) -> None:
        self.segment_name = segment_name

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
        _all_tools: list[Any] = config.registry.get_all_tools()
        valid_segments = {t.scan_segment for t in _all_tools}
        if self.segment_name not in valid_segments:
            raise InvalidSegmentError(self.segment_name, sorted(valid_segments))
        if self.segment_name == "network":
            return NetworkSegmentScan().execute(config)
        return RepoSegmentScan(
            _tools_for_segment(self.segment_name, config.registry)
        ).execute(config)

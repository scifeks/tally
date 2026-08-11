"""Unit tests for ffuf result merging and consolidation."""

from domain.tools.base import ToolResult
from infrastructure.tools.wrappers.base.ffuf import BaseFFufTool


class TestMergePassResults:
    """merge_pass_results combines findings from multiple passes."""

    def _make_result(self, findings, duration=1.0):
        return ToolResult(
            tool_name="ffuf",
            success=True,
            output="",
            parsed_data={
                "findings": findings,
                "summary": {"total_findings": len(findings)},
            },
            output_files={},
            timestamp="2025-01-01T00:00:00",
            duration_seconds=duration,
        )

    def test_merges_findings_from_multiple_passes(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        r2 = self._make_result([{"url": "http://x/b", "status": 200}])
        merged = tool.merge_pass_results([r1, r2])
        assert merged.parsed_data is not None
        assert len(merged.parsed_data["findings"]) == 2

    def test_deduplicates_by_url_and_status(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        r2 = self._make_result([{"url": "http://x/a", "status": 200}])
        merged = tool.merge_pass_results([r1, r2])
        assert merged.parsed_data is not None
        assert len(merged.parsed_data["findings"]) == 1

    def test_keeps_different_status_same_url(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        r2 = self._make_result([{"url": "http://x/a", "status": 403}])
        merged = tool.merge_pass_results([r1, r2])
        assert merged.parsed_data is not None
        assert len(merged.parsed_data["findings"]) == 2

    def test_sums_duration(self):
        tool = BaseFFufTool()
        r1 = self._make_result([], duration=2.5)
        r2 = self._make_result([], duration=3.5)
        merged = tool.merge_pass_results([r1, r2])
        assert merged.duration_seconds == 6.0

    def test_single_pass_returns_as_is(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        merged = tool.merge_pass_results([r1])
        assert merged is r1

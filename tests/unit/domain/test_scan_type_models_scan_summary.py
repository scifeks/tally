"""Unit tests for ScanSummary dataclass."""

from __future__ import annotations

from domain.tools.scan_types.models import ScanSummary


class TestScanSummary:
    def test_field_access(self) -> None:
        s = ScanSummary(
            total_tools_run=3,
            total_tools_skipped=1,
            total_tools_failed=0,
            results=[],
            duration_seconds=2.5,
            findings_ingested=10,
        )
        assert s.total_tools_run == 3
        assert s.total_tools_skipped == 1
        assert s.total_tools_failed == 0
        assert s.results == []
        assert s.duration_seconds == 2.5
        assert s.findings_ingested == 10

    def test_findings_by_tool_defaults_to_empty_dict(self) -> None:
        s = ScanSummary(
            total_tools_run=0,
            total_tools_skipped=0,
            total_tools_failed=0,
            results=[],
            duration_seconds=0.0,
            findings_ingested=0,
        )
        assert s.findings_by_tool == {}

    def test_findings_by_tool_can_be_set(self) -> None:
        s = ScanSummary(
            total_tools_run=1,
            total_tools_skipped=0,
            total_tools_failed=0,
            results=[],
            duration_seconds=1.0,
            findings_ingested=5,
            findings_by_tool={"semgrep": 5},
        )
        assert s.findings_by_tool == {"semgrep": 5}

    def test_equality(self) -> None:
        def _make() -> ScanSummary:
            return ScanSummary(
                total_tools_run=1,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                duration_seconds=1.0,
                findings_ingested=0,
            )

        assert _make() == _make()

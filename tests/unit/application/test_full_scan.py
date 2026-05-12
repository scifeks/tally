"""Unit tests for FullScan (application.tools.scan_types.full)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.models import ScanTypeConfig
from application.tools.scan_types.resources import ExecutionResources
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.scan_types.models import ScanSummary

_TOOL_CONFIG = ToolExecutionConfig(noir_provider=None)


def _zero_summary() -> ScanSummary:
    return ScanSummary(
        total_tools_run=0,
        total_tools_skipped=0,
        total_tools_failed=0,
        results=[],
        duration_seconds=0.0,
        findings_ingested=0,
        findings_by_tool={},
    )


@pytest.fixture()
def mock_config() -> Any:
    prompt = MagicMock()
    prompt.confirm.return_value = True
    prompt.approve_all_remaining.return_value = None
    return ScanTypeConfig(
        project_name="test-project",
        base_path="/tmp/test",
        tool_config=_TOOL_CONFIG,
        run_id=1,
        prompt=prompt,
    )


@pytest.fixture()
def mock_resources() -> Any:
    registry = MagicMock()
    registry.get_all_tools.return_value = []
    registry.get_tool.return_value = None
    registry.get_tool_config.return_value = None
    return ExecutionResources(
        executor=MagicMock(),
        registry=registry,
        factory=MagicMock(),
        event_bus=MagicMock(),
        display=MagicMock(),
    )


class TestFullScan:
    def test_all_segments_excluded_returns_zero_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.full import FullScan

        with patch("application.tools.scan_types.full.RepoSegmentScan") as mock_repo:
            summary = FullScan(
                exclude_segments=["sast", "sca", "secrets", "web"]
            ).execute(mock_config, mock_resources)

        assert summary.total_tools_run == 0
        assert summary.findings_ingested == 0
        mock_repo.assert_not_called()

    def test_excluded_segment_calls_print_status(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.full import FullScan

        with (
            patch("application.tools.scan_types.full.RepoSegmentScan") as mock_repo,
            patch(
                "application.tools.scan_types.full.tools_for_segment",
                return_value=[],
            ),
        ):
            mock_repo.return_value.execute.return_value = _zero_summary()
            summary = FullScan(exclude_segments=["sast"]).execute(
                mock_config, mock_resources
            )

        assert summary is not None

    def test_aggregates_sub_summary_totals(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.full import FullScan

        sub = ScanSummary(
            total_tools_run=2,
            total_tools_skipped=0,
            total_tools_failed=0,
            results=[],
            duration_seconds=1.0,
            findings_ingested=3,
            findings_by_tool={"semgrep": 3},
        )
        with (
            patch("application.tools.scan_types.full.RepoSegmentScan") as mock_repo,
            patch(
                "application.tools.scan_types.full.tools_for_segment",
                return_value=["semgrep"],
            ),
        ):
            mock_repo.return_value.execute.return_value = sub
            summary = FullScan(exclude_segments=["secrets", "web", "llm"]).execute(
                mock_config, mock_resources
            )

        assert summary.total_tools_run == 4
        assert summary.findings_ingested == 6

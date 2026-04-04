"""Unit tests for FullScan (application.tools.scan_types.full)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig


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


def _make_mock_repo(
    name: str = "my-repo",
    languages: list[str] | None = None,
    base_urls: list[str] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.languages = languages if languages is not None else ["python"]
    repo.base_urls = base_urls
    return repo


@pytest.fixture()
def mock_config() -> Any:
    cm = MagicMock()
    cm.load_repositories.return_value = [_make_mock_repo()]
    return ScanTypeConfig(
        project_name="test-project",
        base_path="/tmp/test",
        config_manager=cm,
        run_id=1,
        auto_approve=True,
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
                exclude_segments=["sast", "sca", "secrets", "api"]
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
            FullScan(exclude_segments=["sast"]).execute(mock_config, mock_resources)

        calls = [
            str(call) for call in mock_resources.display.print_status.call_args_list
        ]
        assert any("sast" in c for c in calls)

    def test_delegates_repo_segment_to_repo_segment_scan(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.full import FullScan

        with (
            patch("application.tools.scan_types.full.RepoSegmentScan") as mock_repo,
            patch(
                "application.tools.scan_types.full.tools_for_segment",
                return_value=["semgrep"],
            ),
        ):
            mock_repo.return_value.execute.return_value = _zero_summary()
            FullScan(exclude_segments=["sca", "secrets", "api"]).execute(
                mock_config, mock_resources
            )

        mock_repo.assert_called_once_with(["semgrep"])

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
                return_value=[],
            ),
        ):
            mock_repo.return_value.execute.return_value = sub
            summary = FullScan(exclude_segments=["secrets", "api"]).execute(
                mock_config, mock_resources
            )

        assert summary.total_tools_run == 4
        assert summary.findings_ingested == 6

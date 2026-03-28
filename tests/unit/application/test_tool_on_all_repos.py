"""Unit tests for ToolOnAllReposScan."""

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
    nmap_cfg = MagicMock()
    nmap_cfg.profiles = {"default": {}}
    cm.load_nmap_hosts.return_value = nmap_cfg
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


class TestToolOnAllReposScan:
    def test_delegates_to_repo_segment_scan_with_tool_name(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_all_repos import ToolOnAllReposScan

        with patch(
            "application.tools.scan_types.tool_on_all_repos.RepoSegmentScan"
        ) as mock_repo:
            mock_repo.return_value.execute.return_value = _zero_summary()
            ToolOnAllReposScan("semgrep").execute(mock_config, mock_resources)

        mock_repo.assert_called_once_with(["semgrep"])

    def test_returns_summary_wrapping_sub_scan_totals(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_all_repos import ToolOnAllReposScan

        sub = ScanSummary(
            total_tools_run=3,
            total_tools_skipped=1,
            total_tools_failed=0,
            results=[],
            duration_seconds=2.0,
            findings_ingested=5,
            findings_by_tool={"semgrep": 5},
        )
        with patch(
            "application.tools.scan_types.tool_on_all_repos.RepoSegmentScan"
        ) as mock_repo:
            mock_repo.return_value.execute.return_value = sub
            summary = ToolOnAllReposScan("semgrep").execute(mock_config, mock_resources)

        assert summary.total_tools_run == 3
        assert summary.findings_ingested == 5

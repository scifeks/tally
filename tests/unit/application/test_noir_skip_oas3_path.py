"""Unit tests for Noir skip logic in RepoSegmentScan.

Covers:
- oas3_path set → Noir skipped with "skipped (endpoint file configured)"
- node_app=True, oas3_path='' → Noir skipped with "skipped (Node.js app)"
- neither set → Noir is NOT skipped by these checks (execute_tool_passes called)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.scan_types.models import ScanTypeConfig


def _make_noir_tool() -> MagicMock:
    t = MagicMock()
    t.name = "noir"
    t.scan_segment = "endpoint"
    t.always_run = True
    t.language_gates = []
    t.requires_base_urls = False
    t.check_available.return_value = True
    t.count_findings.return_value = 0
    t.findings_exit_ok = False
    t.skip = False
    return t


def _make_repo(oas3_path: str = "", node_app: bool = False) -> MagicMock:
    repo = MagicMock()
    repo.name = "my-repo"
    repo.languages = ["python"]
    repo.base_urls = ["http://example.com"]
    repo.oas3_path = oas3_path
    repo.node_app = node_app
    return repo


def _make_config(repo: MagicMock) -> ScanTypeConfig:
    cm = MagicMock()
    cm.load_repositories.return_value = [repo]
    return ScanTypeConfig(
        project_name="test",
        base_path="/tmp/test",
        config_manager=cm,
        run_id=1,
        auto_approve=True,
    )


def _make_resources(noir_tool: MagicMock) -> Any:
    registry = MagicMock()
    registry.get_all_tools.return_value = []
    registry.get_tool.return_value = None
    registry.get_tool_config.return_value = MagicMock()
    factory = MagicMock()
    factory.create.return_value = noir_tool
    return ExecutionResources(
        executor=MagicMock(),
        registry=registry,
        factory=factory,
        event_bus=MagicMock(),
        display=MagicMock(),
    )


class TestNoirSkipOas3Path:
    def test_noir_skipped_when_oas3_path_set(self) -> None:
        """Noir is skipped with 'endpoint file configured' reason."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(oas3_path="/endpoints/api.json")
        config = _make_config(repo)
        resources = _make_resources(noir)

        summary = RepoSegmentScan(["noir"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0
        row = resources.display.print_tool_line.call_args[0][0]
        assert row.skip_reason == "skipped (endpoint file configured)"

    def test_noir_skipped_for_node_app_when_no_oas3_path(self) -> None:
        """Node.js check still fires when oas3_path is empty."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(oas3_path="", node_app=True)
        config = _make_config(repo)
        resources = _make_resources(noir)

        summary = RepoSegmentScan(["noir"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0
        row = resources.display.print_tool_line.call_args[0][0]
        assert row.skip_reason == "skipped (Node.js app)"

    def test_noir_not_skipped_when_neither_set(self) -> None:
        """Neither check fires — execute_tool_passes is called."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(oas3_path="", node_app=False)
        config = _make_config(repo)
        resources = _make_resources(noir)

        patch_target = "application.tools.scan_types.repo_segment.execute_tool_passes"
        with patch(patch_target, return_value=None) as mock_exec:
            RepoSegmentScan(["noir"]).execute(config, resources)

        mock_exec.assert_called_once()

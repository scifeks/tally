"""Unit tests for live crawler (Noir/Katana) skip logic in RepoSegmentScan.

Covers:
- crawl_enabled=False → Noir/Katana skipped with "skipped (live crawling disabled)"
- crawl_enabled=True + oas3_path set → Noir runs (oas3_path alone no longer gates)
- node_app detected → Noir skipped with "skipped (Node.js app)"
- neither skip condition → execute_tool_passes called
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


def _make_katana_tool() -> MagicMock:
    t = MagicMock()
    t.name = "katana"
    t.scan_segment = "endpoint"
    t.always_run = False
    t.language_gates = []
    t.requires_base_urls = True
    t.check_available.return_value = True
    t.count_findings.return_value = 0
    t.findings_exit_ok = False
    t.skip = False
    return t


def _make_repo(
    oas3_path: str = "",
    path: str = "",
    crawl_enabled: bool = True,
) -> MagicMock:
    repo = MagicMock()
    repo.name = "my-repo"
    repo.languages = ["python"]
    repo.base_urls = ["http://example.com"]
    repo.oas3_path = oas3_path
    repo.path = path
    repo.crawl_enabled = crawl_enabled
    return repo


def _make_config(repo: MagicMock) -> ScanTypeConfig:
    cm = MagicMock()
    cm.load_repositories.return_value = [repo]
    prompt = MagicMock()
    prompt.confirm.return_value = True
    prompt.approve_all_remaining.return_value = None
    return ScanTypeConfig(
        project_name="test",
        base_path="/tmp/test",
        config_manager=cm,
        run_id=1,
        prompt=prompt,
    )


def _make_resources(tool: MagicMock) -> Any:
    registry = MagicMock()
    registry.get_all_tools.return_value = []
    registry.get_tool.return_value = None
    registry.get_tool_config.return_value = MagicMock()
    factory = MagicMock()
    factory.create.return_value = tool
    return ExecutionResources(
        executor=MagicMock(),
        registry=registry,
        factory=factory,
        event_bus=MagicMock(),
        display=MagicMock(),
    )


class TestLiveCrawlerSkipOnCrawlDisabled:
    def test_noir_skipped_when_crawl_disabled(self) -> None:
        """crawl_enabled=False skips Noir with 'live crawling disabled'."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(crawl_enabled=False)
        config = _make_config(repo)
        resources = _make_resources(noir)

        summary = RepoSegmentScan(["noir"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0
        row = resources.display.print_tool_line.call_args[0][0]
        assert row.skip_reason == "skipped (live crawling disabled)"

    def test_katana_skipped_when_crawl_disabled(self) -> None:
        """crawl_enabled=False skips Katana with 'live crawling disabled'."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        katana = _make_katana_tool()
        repo = _make_repo(crawl_enabled=False)
        config = _make_config(repo)
        resources = _make_resources(katana)

        summary = RepoSegmentScan(["katana"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0
        row = resources.display.print_tool_line.call_args[0][0]
        assert row.skip_reason == "skipped (live crawling disabled)"

    def test_noir_runs_when_oas3_path_set_and_crawl_enabled(self) -> None:
        """oas3_path alone does not skip Noir when crawl_enabled=True."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(oas3_path="/endpoints/api.json", crawl_enabled=True)
        config = _make_config(repo)
        resources = _make_resources(noir)

        patch_target = "application.tools.scan_types.repo_segment.execute_tool_passes"
        with patch(patch_target, return_value=None) as mock_exec:
            RepoSegmentScan(["noir"]).execute(config, resources)

        mock_exec.assert_called_once()


class TestNoirSkipIncompatTechs:
    def test_noir_skipped_for_node_app_when_no_oas3_path(self, tmp_path: Any) -> None:
        """Node.js auto-detection fires when package.json is present."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        noir = _make_noir_tool()
        repo = _make_repo(path=str(tmp_path), crawl_enabled=True)
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
        repo = _make_repo(crawl_enabled=True)
        config = _make_config(repo)
        resources = _make_resources(noir)

        patch_target = "application.tools.scan_types.repo_segment.execute_tool_passes"
        with patch(patch_target, return_value=None) as mock_exec:
            RepoSegmentScan(["noir"]).execute(config, resources)

        mock_exec.assert_called_once()

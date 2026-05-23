"""Unit tests for live crawler skip logic."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from application.tools.scan_types.models import ScanTypeConfig
from application.tools.scan_types.resources import ExecutionResources
from domain.tools.execution_config import ToolExecutionConfig


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
    repo.path = path
    repo.oas3_path = oas3_path
    service = MagicMock()
    service.languages = ["python"]
    service.base_urls = ["http://example.com"]
    service.crawl_enabled = crawl_enabled
    service.docker_path = ""
    service.relative_path = ""
    service.dependencies_file = ""
    repo.services = [service]
    return repo


def _make_config(repo_repo: MagicMock | None = None) -> ScanTypeConfig:
    prompt = MagicMock()
    prompt.confirm.return_value = True
    prompt.approve_all_remaining.return_value = None
    return ScanTypeConfig(
        project_name="test",
        base_path="/tmp/test",
        tool_config=ToolExecutionConfig(noir_provider=None),
        run_id=1,
        prompt=prompt,
        repo_repo=repo_repo,
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


_EXEC_PASSES = "application.tools.scan_types.repo_segment.execute_tool_passes"


class TestLiveCrawlerSkipOnCrawlDisabled:
    def test_noir_skipped_when_crawl_disabled(self) -> None:
        """crawl_enabled=False skips Noir with 'live crawling disabled'."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(crawl_enabled=False)
        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [repo]
        config = _make_config(repo_repo=repo_repo)
        resources = _make_resources(noir)

        summary = RepoSegmentScan(["noir"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0

    def test_katana_skipped_when_crawl_disabled(self) -> None:
        """crawl_enabled=False skips Katana with 'live crawling disabled'."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        katana = _make_katana_tool()
        repo = _make_repo(crawl_enabled=False)
        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [repo]
        config = _make_config(repo_repo=repo_repo)
        resources = _make_resources(katana)

        summary = RepoSegmentScan(["katana"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0

    def test_noir_runs_when_oas3_path_set_and_crawl_enabled(self) -> None:
        """oas3_path alone does not skip Noir when crawl_enabled=True."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(oas3_path="/endpoints/api.json", crawl_enabled=True)
        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [repo]
        config = _make_config(repo_repo=repo_repo)
        resources = _make_resources(noir)

        with patch(_EXEC_PASSES, return_value=None) as mock_exec:
            RepoSegmentScan(["noir"]).execute(config, resources)

        mock_exec.assert_called_once()


class TestNoirSkipIncompatTechs:
    def test_noir_skipped_for_node_app_when_no_oas3_path(self, tmp_path: Any) -> None:
        """Node.js auto-detection fires when package.json is present."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        noir = _make_noir_tool()
        repo = _make_repo(path=str(tmp_path), crawl_enabled=True)
        repo.services[0].languages = ["node"]
        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [repo]
        config = _make_config(repo_repo=repo_repo)
        resources = _make_resources(noir)

        summary = RepoSegmentScan(["noir"]).execute(config, resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0

    def test_noir_not_skipped_when_neither_set(self) -> None:
        """Neither check fires; execute_tool_passes is called."""
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        noir = _make_noir_tool()
        repo = _make_repo(crawl_enabled=True)
        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [repo]
        config = _make_config(repo_repo=repo_repo)
        resources = _make_resources(noir)

        with patch(_EXEC_PASSES, return_value=None) as mock_exec:
            RepoSegmentScan(["noir"]).execute(config, resources)

        mock_exec.assert_called_once()

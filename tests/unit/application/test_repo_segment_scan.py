"""Unit tests for RepoSegmentScan (application.tools.scan_types.repo_segment)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.scan_types.models import ScanTypeConfig


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


def _make_mock_tool_obj(
    name: str = "test-tool",
    scan_segment: str = "sast",
    always_run: bool = True,
    language_gates: list[str] | None = None,
) -> MagicMock:
    t = MagicMock()
    t.name = name
    t.scan_segment = scan_segment
    t.always_run = always_run
    t.language_gates = language_gates or []
    t.requires_base_urls = False
    t.check_available.return_value = True
    t.count_findings.return_value = 0
    t.findings_exit_ok = False
    t.skip = False
    return t


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
        event_bus=MagicMock(),
        display=MagicMock(),
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
    )


class TestRepoSegmentScan:
    def test_no_repos_returns_skipped_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        mock_config.config_manager.load_repositories.return_value = []
        summary = RepoSegmentScan(["semgrep"]).execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1
        assert summary.total_tools_run == 0

    def test_language_gated_tool_skipped_for_wrong_language(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        java_tool = _make_mock_tool_obj(name="semgrep", language_gates=["java"])
        mock_resources.registry.get_all_tools.return_value = [java_tool]
        mock_resources.registry.get_tool.return_value = java_tool

        summary = RepoSegmentScan(["semgrep"]).execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_tool_not_registered_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        mock_tool = _make_mock_tool_obj(language_gates=[])
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool_config.return_value = None

        summary = RepoSegmentScan(["test-tool"]).execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_factory_error_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        mock_tool = _make_mock_tool_obj(language_gates=[])
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        mock_resources.factory.create.side_effect = RuntimeError("bad module")

        summary = RepoSegmentScan(["test-tool"]).execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_tool_not_available_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        mock_tool = _make_mock_tool_obj(language_gates=[])
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        created_tool = MagicMock()
        created_tool.check_available.return_value = False
        created_tool.requires_base_urls = False
        mock_resources.factory.create.return_value = created_tool

        summary = RepoSegmentScan(["test-tool"]).execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

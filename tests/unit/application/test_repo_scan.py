"""Unit tests for RepoScan (application.tools.scan_types.repo)."""

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


class TestRepoScan:
    def test_repo_not_found_raises_value_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_config.config_manager.load_repositories.return_value = []
        with pytest.raises(ValueError, match="missing"):
            RepoScan("missing").execute(mock_config, mock_resources)

    def test_tool_not_registered_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_tool = _make_mock_tool_obj("test-tool", "sast", always_run=True)
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool.return_value = mock_tool
        mock_resources.registry.get_tool_config.return_value = None

        summary = RepoScan("my-repo").execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_factory_error_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_tool = _make_mock_tool_obj("test-tool", "sast", always_run=True)
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool.return_value = mock_tool
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        mock_resources.factory.create.side_effect = Exception("bad")

        summary = RepoScan("my-repo").execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_tool_not_available_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_tool = _make_mock_tool_obj("test-tool", "sast", always_run=True)
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool.return_value = mock_tool
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        created_tool = MagicMock()
        created_tool.check_available.return_value = False
        created_tool.requires_base_urls = False
        mock_resources.factory.create.return_value = created_tool

        summary = RepoScan("my-repo").execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

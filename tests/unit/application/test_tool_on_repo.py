"""Unit tests for ToolOnRepoScan (application.tools.scan_types.tool_on_repo)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.scan_types.models import ScanTypeConfig

_LOAD_REPOS = "application.tools.scan_types.tool_on_repo.load_active_repos"
_TOOL_CONFIG = ToolExecutionConfig(noir_provider=None)


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


class TestToolOnRepoScan:
    def test_repo_not_found_raises_value_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_repo import ToolOnRepoScan

        with patch(_LOAD_REPOS, return_value=[]):
            with pytest.raises(ValueError, match="missing-repo"):
                ToolOnRepoScan("semgrep", "missing-repo").execute(
                    mock_config, mock_resources
                )

    def test_tool_not_registered_raises_value_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_repo import ToolOnRepoScan

        mock_resources.registry.get_tool_config.return_value = None
        with patch(_LOAD_REPOS, return_value=[_make_mock_repo()]):
            with pytest.raises(ValueError, match="not registered"):
                ToolOnRepoScan("semgrep", "my-repo").execute(
                    mock_config, mock_resources
                )

    def test_factory_error_raises_value_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_repo import ToolOnRepoScan

        mock_resources.registry.get_tool_config.return_value = MagicMock()
        mock_resources.factory.create.side_effect = RuntimeError("bad")
        with patch(_LOAD_REPOS, return_value=[_make_mock_repo()]):
            with pytest.raises(ValueError, match="factory error"):
                ToolOnRepoScan("semgrep", "my-repo").execute(
                    mock_config, mock_resources
                )

    def test_tool_not_available_raises_value_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_repo import ToolOnRepoScan

        mock_resources.registry.get_tool_config.return_value = MagicMock()
        tool = MagicMock()
        tool.check_available.return_value = False
        mock_resources.factory.create.return_value = tool
        with patch(_LOAD_REPOS, return_value=[_make_mock_repo()]):
            with pytest.raises(ValueError, match="not installed"):
                ToolOnRepoScan("semgrep", "my-repo").execute(
                    mock_config, mock_resources
                )

    def test_requires_base_urls_raises_when_empty(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.tool_on_repo import ToolOnRepoScan

        mock_resources.registry.get_tool_config.return_value = MagicMock()
        tool = MagicMock()
        tool.check_available.return_value = True
        tool.requires_base_urls = True
        mock_resources.factory.create.return_value = tool
        with patch(_LOAD_REPOS, return_value=[_make_mock_repo(base_urls=[])]):
            with pytest.raises(ValueError, match="requires base_urls"):
                ToolOnRepoScan("zap", "my-repo").execute(mock_config, mock_resources)

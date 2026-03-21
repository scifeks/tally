"""Unit tests for NetworkSegmentScan (application.tools.scan_types.network_segment)."""

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


class TestNetworkSegmentScan:
    def test_no_nmap_config_returns_skipped_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.network_segment import NetworkSegmentScan

        mock_config.config_manager.load_nmap_hosts.return_value = None
        summary = NetworkSegmentScan().execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_empty_profiles_returns_skipped_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.network_segment import NetworkSegmentScan

        mock_config.config_manager.load_nmap_hosts.return_value = MagicMock(profiles={})
        summary = NetworkSegmentScan().execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_nmap_not_registered_returns_skipped_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.network_segment import NetworkSegmentScan

        mock_config.config_manager.load_nmap_hosts.return_value = MagicMock(
            profiles={"d": {}}
        )
        mock_resources.registry.get_tool_config.return_value = None
        summary = NetworkSegmentScan().execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_factory_error_returns_skipped_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.network_segment import NetworkSegmentScan

        mock_config.config_manager.load_nmap_hosts.return_value = MagicMock(
            profiles={"d": {}}
        )
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        mock_resources.factory.create.side_effect = RuntimeError("err")
        summary = NetworkSegmentScan().execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_nmap_not_available_returns_skipped_summary(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.network_segment import NetworkSegmentScan

        mock_config.config_manager.load_nmap_hosts.return_value = MagicMock(
            profiles={"d": {}}
        )
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        tool = MagicMock()
        tool.check_available.return_value = False
        mock_resources.factory.create.return_value = tool
        summary = NetworkSegmentScan().execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

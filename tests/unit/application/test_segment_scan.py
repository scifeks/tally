"""Unit tests for SegmentScan (application.tools.scan_types.segment)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.exceptions import InvalidSegmentError
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


class TestSegmentScan:
    def test_invalid_segment_raises_invalid_segment_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.segment import SegmentScan

        mock_resources.registry.get_all_tools.return_value = [
            _make_mock_tool_obj(scan_segment="sast")
        ]
        with pytest.raises(InvalidSegmentError):
            SegmentScan("unknown").execute(mock_config, mock_resources)

    def test_valid_network_segment_delegates_to_network_scan(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.segment import SegmentScan

        mock_resources.registry.get_all_tools.return_value = [
            _make_mock_tool_obj(scan_segment="network")
        ]
        with patch(
            "application.tools.scan_types.segment.NetworkSegmentScan"
        ) as mock_net:
            mock_net.return_value.execute.return_value = _zero_summary()
            SegmentScan("network").execute(mock_config, mock_resources)

        mock_net.assert_called_once()
        mock_net.return_value.execute.assert_called_once()

    def test_valid_repo_segment_delegates_to_repo_segment_scan(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.segment import SegmentScan

        mock_resources.registry.get_all_tools.return_value = [
            _make_mock_tool_obj(scan_segment="sast")
        ]
        with (
            patch("application.tools.scan_types.segment.RepoSegmentScan") as mock_repo,
            patch(
                "application.tools.scan_types.segment._tools_for_segment",
                return_value=["semgrep"],
            ),
        ):
            mock_repo.return_value.execute.return_value = _zero_summary()
            SegmentScan("sast").execute(mock_config, mock_resources)

        mock_repo.assert_called_once_with(["semgrep"])

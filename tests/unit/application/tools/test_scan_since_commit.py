"""Tests for since_commit pipeline threading."""

from __future__ import annotations

from unittest.mock import Mock

from application.ports.git_diff import GitDiffPort
from application.tools.scan_types.models import ScanTypeConfig
from domain.tools.execution_config import ToolExecutionConfig


class TestScanTypeConfigSinceCommit:
    def test_accepts_since_commit(self) -> None:
        config = ScanTypeConfig(
            project_name="test",
            base_path="/tmp",
            tool_config=ToolExecutionConfig(noir_provider=None),
            run_id=1,
            prompt=Mock(),
            since_commit="abc123",
        )
        assert config.since_commit == "abc123"

    def test_defaults_to_none(self) -> None:
        config = ScanTypeConfig(
            project_name="test",
            base_path="/tmp",
            tool_config=ToolExecutionConfig(noir_provider=None),
            run_id=1,
            prompt=Mock(),
        )
        assert config.since_commit is None
        assert config.git_diff is None

    def test_accepts_git_diff_port(self) -> None:
        diff = Mock(spec=GitDiffPort)
        config = ScanTypeConfig(
            project_name="test",
            base_path="/tmp",
            tool_config=ToolExecutionConfig(noir_provider=None),
            run_id=1,
            prompt=Mock(),
            git_diff=diff,
        )
        assert config.git_diff is diff

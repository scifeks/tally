"""Unit tests for domain.tool_overrides.entry dataclasses."""

from __future__ import annotations

import pytest

from domain.tool_overrides.entry import ToolOverride


class TestToolOverride:
    def test_local_override_has_path_no_container(self) -> None:
        override = ToolOverride(
            id=7,
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/local/bin/semgrep",
            container_name=None,
            container_tool_path=None,
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        assert override.location == "local"
        assert override.path == "/usr/local/bin/semgrep"
        assert override.container_name is None
        assert override.container_tool_path is None

    def test_docker_override_has_container_no_path(self) -> None:
        override = ToolOverride(
            id=8,
            tool_name="semgrep",
            args_mode="custom",
            type="repo",
            location="docker",
            path=None,
            container_name="tally-semgrep",
            container_tool_path="/usr/local/bin/semgrep",
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        assert override.location == "docker"
        assert override.path is None
        assert override.container_name == "tally-semgrep"
        assert override.container_tool_path == "/usr/local/bin/semgrep"
        assert override.args_mode == "custom"

    def test_is_frozen(self) -> None:
        override = ToolOverride(
            id=1,
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
            container_name=None,
            container_tool_path=None,
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        with pytest.raises(Exception):
            override.tool_name = "other"  # type: ignore[misc]

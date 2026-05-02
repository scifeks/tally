"""Unit tests for build_tool_table (REPL adapter)."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console
from rich.table import Table

from application.repl.adapters.tool_registry_display import build_tool_table
from application.tools.registry import ToolRegistry


def _local_tool(name: str, category: str, *, available: bool = True) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.category = category
    tool.check_available.return_value = available
    tool.get_version.return_value = f"{name} 1.0" if available else None
    return tool


class TestBuildToolTable:
    def _registry_for(self, tools_and_configs: list[tuple]) -> ToolRegistry:
        reg = ToolRegistry()
        for tool, cfg in tools_and_configs:
            reg.register(tool, config=cfg)
        return reg

    def test_returns_rich_table(self) -> None:
        tool = _local_tool("semgrep", "sast")
        cfg = MagicMock(location="local")
        reg = self._registry_for([(tool, cfg)])
        result = build_tool_table([tool], reg)
        assert isinstance(result, Table)

    def test_row_count_matches_tool_count(self) -> None:
        t1 = _local_tool("semgrep", "sast")
        t2 = _local_tool("gitleaks", "secrets", available=False)
        cfg = MagicMock(location="local")
        reg = self._registry_for([(t1, cfg), (t2, cfg)])
        table = build_tool_table([t1, t2], reg)
        assert table.row_count == 2

    def test_unavailable_local_tool_shows_not_found(self) -> None:
        tool = _local_tool("missing-tool", "sast", available=False)
        cfg = MagicMock(location="local")
        reg = self._registry_for([(tool, cfg)])
        buf = StringIO()
        console = Console(file=buf, highlight=False, no_color=True)
        table = build_tool_table([tool], reg)
        console.print(table)
        assert "NOT FOUND" in buf.getvalue()

    def test_docker_tool_shows_configured(self) -> None:
        tool = MagicMock()
        tool.name = "zap"
        tool.category = "api"
        container_mock = MagicMock()
        container_mock.name = "zap-container"
        cfg = MagicMock(location="docker", container=container_mock)
        reg = self._registry_for([(tool, cfg)])
        buf = StringIO()
        console = Console(file=buf, highlight=False, no_color=True)
        table = build_tool_table([tool], reg)
        console.print(table)
        output = buf.getvalue()
        assert "configured" in output.lower()
        assert "zap-container" in output

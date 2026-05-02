"""Unit tests for print_discovery_summary (REPL adapter)."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console

from application.repl.adapters.tool_registry_display import print_discovery_summary
from application.tools.registry import ToolRegistry


def _local_tool(name: str, category: str, *, available: bool = True) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.category = category
    tool.check_available.return_value = available
    tool.get_version.return_value = f"{name} 1.0" if available else None
    return tool


class TestPrintDiscoverySummary:
    def _patched_registry(self, tools: list) -> ToolRegistry:
        reg = ToolRegistry()
        for tool in tools:
            reg.register(tool)
        return reg

    def test_output_contains_configured_tools_header(self) -> None:
        t1 = _local_tool("semgrep", "sast")
        t2 = _local_tool("gitleaks", "secrets")
        reg = self._patched_registry([t1, t2])
        buf = StringIO()
        console = Console(file=buf, highlight=False, no_color=True)
        with patch(
            "application.repl.adapters.tool_registry_display.tool_registry", reg
        ):
            print_discovery_summary(console)
        assert "Configured Tools" in buf.getvalue()

    def test_output_contains_loaded_count(self) -> None:
        t1 = _local_tool("semgrep", "sast")
        t2 = _local_tool("gitleaks", "secrets")
        reg = self._patched_registry([t1, t2])
        buf = StringIO()
        console = Console(file=buf, highlight=False, no_color=True)
        with patch(
            "application.repl.adapters.tool_registry_display.tool_registry", reg
        ):
            print_discovery_summary(console)
        assert "Loaded 2 tools" in buf.getvalue()

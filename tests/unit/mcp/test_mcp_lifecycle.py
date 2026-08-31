"""Unit tests for managed MCP server shutdown."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.mcp.lifecycle import stop_mcp_server
from application.mcp.registry import (
    McpServerHandle,
    McpServerRegistry,
)


class TestStopMcpServer:
    """Tests for stopping the running MCP server via its registry handle."""

    def test_stop_sets_should_exit(self) -> None:
        reg = McpServerRegistry()
        server = MagicMock()
        server.should_exit = False
        handle = McpServerHandle(
            host="127.0.0.1",
            port=8765,
            source="repl",
            server=server,
            thread=MagicMock(),
        )
        reg.register(handle)
        with patch(
            "application.mcp.lifecycle.get_mcp_server_registry",
            return_value=reg,
        ):
            assert stop_mcp_server() is True
        assert server.should_exit is True

    def test_stop_when_not_running(self) -> None:
        reg = McpServerRegistry()
        with patch(
            "application.mcp.lifecycle.get_mcp_server_registry",
            return_value=reg,
        ):
            assert stop_mcp_server() is False

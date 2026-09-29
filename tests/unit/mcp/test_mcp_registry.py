"""Unit tests for the MCP server process registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.mcp.registry import McpServerRegistry


class TestMcpServerRegistry:
    """Tests for tracking the active MCP server handle."""

    def test_starts_empty(self) -> None:
        reg = McpServerRegistry()
        assert reg.is_active() is False
        assert reg.get() is None

    def test_register_and_get(self) -> None:
        reg = McpServerRegistry()
        handle = MagicMock()
        handle.port = 8765
        reg.register(handle)
        assert reg.is_active() is True
        assert reg.get() is handle

    def test_unregister(self) -> None:
        reg = McpServerRegistry()
        reg.register(MagicMock())
        reg.unregister()
        assert reg.is_active() is False

    def test_duplicate_register_raises(self) -> None:
        reg = McpServerRegistry()
        reg.register(MagicMock())
        with pytest.raises(RuntimeError):
            reg.register(MagicMock())

    def test_reset(self) -> None:
        reg = McpServerRegistry()
        reg.register(MagicMock())
        reg.reset()
        assert reg.is_active() is False

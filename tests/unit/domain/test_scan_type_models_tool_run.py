"""Unit tests for ToolRun dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

from domain.tools.scan_types.models import ToolRun


class TestToolRun:
    def test_field_access(self) -> None:
        iface = MagicMock()
        run = ToolRun(tool_interface=iface, profile="default", remaining=5)
        assert run.tool_interface is iface
        assert run.profile == "default"
        assert run.remaining == 5

    def test_equality(self) -> None:
        iface = MagicMock()
        assert ToolRun(iface, "x", 1) == ToolRun(iface, "x", 1)

    def test_inequality_different_remaining(self) -> None:
        iface = MagicMock()
        assert ToolRun(iface, "x", 1) != ToolRun(iface, "x", 2)

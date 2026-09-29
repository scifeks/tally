"""Unit tests for Burp tool registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.tools.registry import ToolRegistry


def _make_registry() -> ToolRegistry:
    return ToolRegistry()


def _mock_config_with_burp():
    config = MagicMock()
    config.global_config.burp = MagicMock()
    config.global_config.burp.base_url = "http://10.1.20.101:1337"
    config.global_config.burp.api_key = ""
    return config


def _mock_config_without_burp():
    config = MagicMock()
    config.global_config.burp = None
    return config


class TestBurpToolRegistration:
    def test_registered_when_config_present_and_healthy(
        self,
    ) -> None:
        from application.tools.registry import (
            register_burp_tool,
        )

        registry = _make_registry()
        with patch(
            "core.config.manager.ConfigManager",
        ) as mock_cm_cls:
            mock_cm_cls.return_value = _mock_config_with_burp()
            with patch(
                "infrastructure.tools.burp.probe.probe_burp_availability",
                return_value=True,
            ):
                register_burp_tool(registry, ".")

        tool = registry.get_tool("burp")
        assert tool is not None
        assert tool.name == "burp"

    def test_not_registered_when_config_absent(
        self,
    ) -> None:
        from application.tools.registry import (
            register_burp_tool,
        )

        registry = _make_registry()
        with patch(
            "core.config.manager.ConfigManager",
        ) as mock_cm_cls:
            mock_cm_cls.return_value = _mock_config_without_burp()
            register_burp_tool(registry, ".")

        assert registry.get_tool("burp") is None

    def test_not_registered_when_offline(self) -> None:
        from application.tools.registry import (
            register_burp_tool,
        )

        registry = _make_registry()
        with patch(
            "core.config.manager.ConfigManager",
        ) as mock_cm_cls:
            mock_cm_cls.return_value = _mock_config_with_burp()
            with patch(
                "infrastructure.tools.burp.probe.probe_burp_availability",
                return_value=False,
            ):
                register_burp_tool(registry, ".")

        assert registry.get_tool("burp") is None

    def test_registered_tool_has_http_transport(
        self,
    ) -> None:
        from application.tools.registry import (
            register_burp_tool,
        )
        from domain.tools.interface import TransportType

        registry = _make_registry()
        with patch(
            "core.config.manager.ConfigManager",
        ) as mock_cm_cls:
            mock_cm_cls.return_value = _mock_config_with_burp()
            with patch(
                "infrastructure.tools.burp.probe.probe_burp_availability",
                return_value=True,
            ):
                register_burp_tool(registry, ".")

        tool = registry.get_tool("burp")
        assert tool is not None
        assert tool.transport == TransportType.HTTP

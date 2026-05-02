"""Tests that discover_tools() registers xsstrike when commands.json contains it.

This test exists to catch the class of bug introduced in TAL-111: all wrapper
files were present but xsstrike was never added to config/commands.json, so
discover_tools() never registered it and scan --tool=xsstrike returned
"Unknown tool(s): xsstrike" immediately.

These tests exercise the full discovery path:
  commands.json on disk → discover_tools() → tool_registry
"""

from __future__ import annotations

import json

from application.tools.registry import discover_tools, tool_registry
from infrastructure.tools.wrappers.local.xsstrike import XSSTrikeLocalTool

_XSSTRIKE_LOCAL_ENTRY = {
    "type": "api",
    "location": "local",
    "path": "/usr/bin/xsstrike",
}


class TestXSSTrikeDiscoveryFromCommandsJson:
    def test_xsstrike_registered_after_discover_tools(self, tmp_path) -> None:
        """discover_tools with a valid xsstrike entry registers the tool."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        assert tool_registry.get_tool("xsstrike") is not None

    def test_xsstrike_registered_tool_is_local_wrapper(self, tmp_path) -> None:
        """Registered tool is the concrete local wrapper, not a stub."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("xsstrike")
        assert isinstance(tool, XSSTrikeLocalTool)

    def test_xsstrike_config_location_is_local(self, tmp_path) -> None:
        """Registered config reflects location=local from commands.json."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        config = tool_registry.get_tool_config("xsstrike")
        assert config is not None
        assert config.location == "local"

    def test_xsstrike_absent_from_commands_json_means_not_registered(
        self, tmp_path
    ) -> None:
        """When xsstrike is omitted from commands.json it is not registered.

        This is the exact failure mode from TAL-111: wrapper files existed but
        commands.json had no entry, so the tool was silently absent from the
        registry.
        """
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps(
                {
                    "semgrep": {
                        "type": "repo",
                        "location": "local",
                        "path": "/usr/bin/semgrep",
                    }
                }
            ),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        assert tool_registry.get_tool("xsstrike") is None

    def test_xsstrike_registered_name_property_is_xsstrike(self, tmp_path) -> None:
        """Wrapper name property matches the registry key."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("xsstrike")
        assert tool is not None
        assert tool.name == "xsstrike"

    def test_xsstrike_in_list_tool_names_after_discover(self, tmp_path) -> None:
        """list_tool_names() includes xsstrike after discovery."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        assert "xsstrike" in tool_registry.list_tool_names()

    def test_xsstrike_scan_segment_is_web(self, tmp_path) -> None:
        """Registered tool has scan_segment='web'; routes to web scan type."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("xsstrike")
        assert tool is not None
        assert tool.scan_segment == "web"

    def test_xsstrike_requires_base_urls_is_true(self, tmp_path) -> None:
        """requires_base_urls=True ensures scan skips repos with no base URLs."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"xsstrike": _XSSTRIKE_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("xsstrike")
        assert tool is not None
        assert tool.requires_base_urls is True

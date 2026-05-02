"""Tests that discover_tools() registers dalfox when commands.json contains it.

This test exists to catch the class of bug introduced in TAL-111: all wrapper
files were present but the tool was never added to config/commands.json, so
discover_tools() never registered it and scan --tool=dalfox returned
"Unknown tool(s): dalfox" immediately.

These tests exercise the full discovery path:
  commands.json on disk → discover_tools() → tool_registry
"""

from __future__ import annotations

import json

from application.tools.registry import discover_tools, tool_registry
from infrastructure.tools.wrappers.local.dalfox import DalFoxLocalTool

_DALFOX_LOCAL_ENTRY = {
    "type": "api",
    "location": "local",
    "path": "/usr/bin/dalfox",
}


class TestDalFoxDiscoveryFromCommandsJson:
    def test_dalfox_registered_after_discover_tools(self, tmp_path) -> None:
        """discover_tools with a valid dalfox entry registers the tool."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        assert tool_registry.get_tool("dalfox") is not None

    def test_dalfox_registered_tool_is_local_wrapper(self, tmp_path) -> None:
        """Registered tool is the concrete local wrapper, not a stub."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("dalfox")
        assert isinstance(tool, DalFoxLocalTool)

    def test_dalfox_config_location_is_local(self, tmp_path) -> None:
        """Registered config reflects location=local from commands.json."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        config = tool_registry.get_tool_config("dalfox")
        assert config is not None
        assert config.location == "local"

    def test_dalfox_absent_from_commands_json_means_not_registered(
        self, tmp_path
    ) -> None:
        """When dalfox is omitted from commands.json it is not registered."""
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

        assert tool_registry.get_tool("dalfox") is None

    def test_dalfox_registered_name_property_is_dalfox(self, tmp_path) -> None:
        """Wrapper name property matches the registry key."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("dalfox")
        assert tool is not None
        assert tool.name == "dalfox"

    def test_dalfox_in_list_tool_names_after_discover(self, tmp_path) -> None:
        """list_tool_names() includes dalfox after discovery."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        assert "dalfox" in tool_registry.list_tool_names()

    def test_dalfox_scan_segment_is_web(self, tmp_path) -> None:
        """Registered tool has scan_segment='web'; routes to web scan type."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("dalfox")
        assert tool is not None
        assert tool.scan_segment == "web"

    def test_dalfox_requires_base_urls_is_true(self, tmp_path) -> None:
        """requires_base_urls=True ensures scan skips repos with no base URLs."""
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps({"dalfox": _DALFOX_LOCAL_ENTRY}),
            encoding="utf-8",
        )

        discover_tools(str(tmp_path))

        tool = tool_registry.get_tool("dalfox")
        assert tool is not None
        assert tool.requires_base_urls is True

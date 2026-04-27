"""Discovery tests for runtime reconciliation of global commands.json."""

from __future__ import annotations

import json
from unittest.mock import patch

from application.tools.registry import discover_tools, tool_registry


class TestRegistryRuntimeReconciliation:
    def test_discover_tools_registers_installed_missing_tool_and_skips_stale_local(
        self, tmp_path
    ) -> None:
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "commands.json").write_text(
            json.dumps(
                {
                    "dalfox": {
                        "type": "api",
                        "location": "local",
                        "path": "skip",
                    }
                }
            ),
            encoding="utf-8",
        )

        with (
            patch(
                "application.setup.commands_setup._discover_wrapper_tools",
                return_value=["dalfox", "semgrep"],
            ),
            patch(
                "application.setup.commands_setup._get_wrapper_meta",
                side_effect=lambda tool_name, location="local": {
                    "candidate_commands": [tool_name],
                    "tool_type": "api" if tool_name == "dalfox" else "repo",
                },
            ),
            patch(
                "application.setup.commands_setup.shutil.which",
                side_effect=lambda value: "/usr/local/bin/semgrep"
                if value == "semgrep"
                else None,
            ),
        ):
            discover_tools(str(tmp_path))

        assert "semgrep" in tool_registry.list_tool_names()
        assert "dalfox" not in tool_registry.list_tool_names()

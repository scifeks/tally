"""Unit tests for commands_setup helpers (application.setup.commands_setup)."""

from __future__ import annotations

import json
from unittest.mock import patch

from application.setup.commands_setup import (
    _has_metachar,
    find_local_binary,
    reconcile_commands_with_system,
    resolve_local_binary,
    sync_commands_config,
)


class TestCommandsSetup:
    def test_find_local_binary_returns_path_when_found(self) -> None:
        with (
            patch(
                "application.setup.commands_setup._get_wrapper_meta",
                return_value={
                    "candidate_commands": ["semgrep"],
                    "tool_type": "repo",
                },
            ),
            patch(
                "application.setup.commands_setup.shutil.which",
                return_value="/usr/local/bin/semgrep",
            ),
        ):
            result = find_local_binary("semgrep")

        assert result == "/usr/local/bin/semgrep"

    def test_find_local_binary_returns_none_when_not_found(self) -> None:
        with (
            patch(
                "application.setup.commands_setup._get_wrapper_meta",
                return_value={
                    "candidate_commands": ["unknowntool"],
                    "tool_type": "repo",
                },
            ),
            patch(
                "application.setup.commands_setup.shutil.which",
                return_value=None,
            ),
        ):
            result = find_local_binary("unknowntool")

        assert result is None

    def test_resolve_local_binary_prefers_valid_configured_path(self) -> None:
        with patch(
            "application.setup.commands_setup.shutil.which",
            side_effect=lambda value: "/opt/semgrep/bin/semgrep"
            if value == "/opt/semgrep/bin/semgrep"
            else None,
        ):
            result = resolve_local_binary(
                "semgrep", configured_path="/opt/semgrep/bin/semgrep"
            )

        assert result == "/opt/semgrep/bin/semgrep"

    def test_reconcile_commands_with_system_adds_installed_missing_tool(self) -> None:
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
            result = reconcile_commands_with_system(
                {
                    "dalfox": {
                        "type": "api",
                        "location": "local",
                        "path": "skip",
                    }
                }
            )

        assert result == {
            "semgrep": {
                "type": "repo",
                "location": "local",
                "path": "/usr/local/bin/semgrep",
            }
        }

    def test_reconcile_commands_with_system_preserves_docker_entries(self) -> None:
        with (
            patch(
                "application.setup.commands_setup._discover_wrapper_tools",
                return_value=["semgrep"],
            ),
            patch(
                "application.setup.commands_setup._get_wrapper_meta",
                return_value={
                    "candidate_commands": ["semgrep"],
                    "tool_type": "repo",
                },
            ),
            patch(
                "application.setup.commands_setup.shutil.which",
                side_effect=lambda value: "/usr/local/bin/semgrep"
                if value == "semgrep"
                else None,
            ),
        ):
            result = reconcile_commands_with_system(
                {
                    "zap": {
                        "type": "api",
                        "location": "docker",
                        "container": {"name": "zap", "tool_path": "/zap/zap.sh"},
                    }
                }
            )

        assert result == {
            "semgrep": {
                "type": "repo",
                "location": "local",
                "path": "/usr/local/bin/semgrep",
            },
            "zap": {
                "type": "api",
                "location": "docker",
                "container": {"name": "zap", "tool_path": "/zap/zap.sh"},
            },
        }

    def test_sync_commands_config_rewrites_global_commands_json(self, tmp_path) -> None:
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
            result = sync_commands_config(str(tmp_path))

        assert result == {
            "semgrep": {
                "type": "repo",
                "location": "local",
                "path": "/usr/local/bin/semgrep",
            }
        }
        assert json.loads((cfg / "commands.json").read_text(encoding="utf-8")) == result

    def test_has_metachar_true_for_semicolon(self) -> None:
        assert _has_metachar("foo;bar") is True

    def test_has_metachar_true_for_pipe(self) -> None:
        assert _has_metachar("foo|bar") is True

    def test_has_metachar_true_for_backtick(self) -> None:
        assert _has_metachar("foo`bar") is True

    def test_has_metachar_true_for_dollar(self) -> None:
        assert _has_metachar("echo $HOME") is True

    def test_has_metachar_false_for_clean_path(self) -> None:
        assert _has_metachar("/usr/local/bin/semgrep") is False

    def test_has_metachar_false_for_empty_string(self) -> None:
        assert _has_metachar("") is False

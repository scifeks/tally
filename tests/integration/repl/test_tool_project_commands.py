"""Tests for project-scoped tool commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.tool_commands import ToolCommands

pytestmark = pytest.mark.integration


def _make_tc(
    active_project: str | None = "myproject",
    base_path: str | None = None,
) -> tuple[ToolCommands, MagicMock]:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = base_path or "/tmp/tally-test"
    return ToolCommands(repl, MagicMock()), repl


# _parse_project_flag


def test_parse_project_flag_extracts_name() -> None:
    tc, _repl = _make_tc()
    project, remaining = tc._parse_project_flag(["add", "--project=foo"])
    assert project == "foo"
    assert remaining == ["add"]


def test_parse_project_flag_absent() -> None:
    tc, _repl = _make_tc()
    original = ["add", "nmap"]
    project, remaining = tc._parse_project_flag(original)
    assert project is None
    assert remaining == original


def test_parse_project_flag_bare_with_active_project() -> None:
    """Bare --project resolves to the active project name."""
    tc, _repl = _make_tc(active_project="DVPA")
    project, remaining = tc._parse_project_flag(["add", "--project"])
    assert project == "DVPA"
    assert remaining == ["add"]


def test_parse_project_flag_bare_without_active_project() -> None:
    """Bare --project with no active project returns empty string (not None).

    The empty string is passed to _validate_project_arg, which surfaces the
    'No active project' error rather than silently falling through to the
    global command path.
    """
    tc, _repl = _make_tc(active_project=None)
    project, remaining = tc._parse_project_flag(["add", "--project"])
    assert project == ""
    assert remaining == ["add"]


def test_tool_add_bare_project_flag_routes_to_project_add(
    tmp_path: Path,
) -> None:
    """tool add --project (without =name) must route to the project-level add.

    Regression: previously bare --project was not recognised, so the command
    fell through to the global _cmd_tool_add, which reported 'All available
    tools are already configured' even though no project-level overrides
    existed.
    """
    project_dir = tmp_path / "projects" / "DVPA" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    # No project-level commands.json; zero project overrides
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "commands.json").write_text("{}")

    tc, repl = _make_tc(active_project="DVPA", base_path=str(tmp_path))

    with (
        patch.object(tc, "_get_wrapper_availability", return_value=({"nmap"}, set())),
        patch("builtins.input", return_value=""),
    ):
        tc.cmd_tool("tool", ["add", "--project"])

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    # Must offer tools to add at project level, not claim everything is done
    assert any("Available tools to add" in c for c in printed_calls)
    # Must NOT emit the global "all configured" message
    assert not any(
        "All available tools are already configured" in c and "project level" not in c
        for c in printed_calls
    )


def test_tool_add_bare_project_flag_no_active_project(tmp_path: Path) -> None:
    """tool add --project with no active project shows 'No active project' error."""
    tc, repl = _make_tc(active_project=None, base_path=str(tmp_path))

    with patch.object(tc, "_get_wrapper_availability", return_value=({"nmap"}, set())):
        tc.cmd_tool("tool", ["add", "--project"])

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("No active project" in c for c in printed_calls)


# _validate_project_arg


def test_validate_project_no_active_project() -> None:
    tc, repl = _make_tc(active_project=None)
    result = tc._validate_project_arg("myproject")
    assert result is False
    printed = repl.console.print.call_args[0][0]
    assert "No active project" in printed


def test_validate_project_not_found(tmp_path: Path) -> None:
    tc, repl = _make_tc(base_path=str(tmp_path))
    result = tc._validate_project_arg("ghost")
    assert result is False
    printed = repl.console.print.call_args[0][0]
    assert "Project not found" in printed


def test_validate_project_found(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    tc, _repl = _make_tc(base_path=str(tmp_path))
    result = tc._validate_project_arg("myproject")
    assert result is True


# tool list --project=<name>


def test_tool_list_project_no_config(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    tc, repl = _make_tc(base_path=str(tmp_path))
    tc._cmd_tool_list_project("myproject")
    printed = repl.console.print.call_args[0][0]
    assert "No project-level tool overrides" in printed


def test_tool_list_project_with_config(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text(
        json.dumps(
            {
                "nmap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/nmap",
                }
            }
        )
    )
    tc, repl = _make_tc(base_path=str(tmp_path))
    tc._cmd_tool_list_project("myproject")
    # Table object is passed to print; just verify print was called
    assert repl.console.print.called


# tool add --project=<name>


def test_tool_add_project_duplicate_in_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text(
        json.dumps(
            {"nmap": {"type": "repo", "location": "local", "path": "/usr/bin/nmap"}}
        )
    )
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "commands.json").write_text("{}")

    tc, repl = _make_tc(base_path=str(tmp_path))

    with (
        patch.object(tc, "_get_wrapper_availability", return_value=({"nmap"}, set())),
        patch("builtins.input", return_value="nmap"),
    ):
        tc._cmd_tool_add_project("myproject")

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("already configured" in c for c in printed_calls)


def test_tool_add_project_warns_global_duplicate(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text("{}")
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "commands.json").write_text(
        json.dumps(
            {"nmap": {"type": "repo", "location": "local", "path": "/usr/bin/nmap"}}
        )
    )

    tc, repl = _make_tc(base_path=str(tmp_path))

    with (
        patch.object(tc, "_get_wrapper_availability", return_value=({"nmap"}, set())),
        patch("builtins.input", return_value="nmap"),
        patch("application.setup.commands_setup.interview_tool", return_value=None),
    ):
        tc._cmd_tool_add_project("myproject")

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("Warning" in c for c in printed_calls)


def test_tool_add_project_saves_entry(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text("{}")
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "commands.json").write_text("{}")

    tc, _repl = _make_tc(base_path=str(tmp_path))

    fake_entry = {"type": "repo", "location": "local", "path": "/usr/bin/nmap"}

    with (
        patch.object(tc, "_get_wrapper_availability", return_value=({"nmap"}, set())),
        patch("builtins.input", return_value="nmap"),
        patch(
            "application.setup.commands_setup.interview_tool", return_value=fake_entry
        ),
    ):
        tc._cmd_tool_add_project("myproject")

    saved = json.loads((project_dir / "commands.json").read_text())
    assert "nmap" in saved
    assert saved["nmap"]["path"] == "/usr/bin/nmap"


# tool edit --project=<name>


def test_tool_edit_project_not_found(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text("{}")

    tc, repl = _make_tc(base_path=str(tmp_path))
    tc._cmd_tool_edit_project("nmap", "myproject")

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("Tool not configured" in c for c in printed_calls)


def test_tool_edit_project_saves_entry(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    existing = {"type": "repo", "location": "local", "path": "/old/nmap"}
    (project_dir / "commands.json").write_text(json.dumps({"nmap": existing}))

    tc, _repl = _make_tc(base_path=str(tmp_path))
    updated = {"type": "repo", "location": "local", "path": "/new/nmap"}

    with (
        patch.object(tc, "_get_wrapper_availability", return_value=({"nmap"}, set())),
        patch("application.setup.commands_setup.interview_tool", return_value=updated),
    ):
        tc._cmd_tool_edit_project("nmap", "myproject")

    saved = json.loads((project_dir / "commands.json").read_text())
    assert saved["nmap"]["path"] == "/new/nmap"


# tool remove --project=<name>


def test_tool_remove_project_not_found(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text("{}")

    tc, repl = _make_tc(base_path=str(tmp_path))
    tc._cmd_tool_remove_project("nmap", "myproject")

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("Tool not configured" in c for c in printed_calls)


def test_tool_remove_project_cancelled(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    existing = {"type": "repo", "location": "local", "path": "/usr/bin/nmap"}
    (project_dir / "commands.json").write_text(json.dumps({"nmap": existing}))

    tc, repl = _make_tc(base_path=str(tmp_path))
    with patch("builtins.input", return_value="n"):
        tc._cmd_tool_remove_project("nmap", "myproject")

    saved = json.loads((project_dir / "commands.json").read_text())
    assert "nmap" in saved
    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("Cancelled" in c for c in printed_calls)


def test_tool_remove_project_confirmed(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    existing = {"type": "repo", "location": "local", "path": "/usr/bin/nmap"}
    (project_dir / "commands.json").write_text(json.dumps({"nmap": existing}))

    tc, _repl = _make_tc(base_path=str(tmp_path))
    with patch("builtins.input", return_value="y"):
        tc._cmd_tool_remove_project("nmap", "myproject")

    saved = json.loads((project_dir / "commands.json").read_text())
    assert "nmap" not in saved


# discover_tools project override


def test_discover_tools_project_override(tmp_path: Path) -> None:
    from application.tools.registry import discover_tools, tool_registry

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/gitleaks",
                }
            }
        )
    )

    project_config = tmp_path / "projects" / "proj" / "config"
    project_config.mkdir(parents=True)
    (project_config / "commands.json").write_text(
        json.dumps(
            {
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/custom/gitleaks",
                }
            }
        )
    )

    try:
        discover_tools(str(tmp_path), project_name="proj")
        config = tool_registry.get_tool_config("gitleaks")
        assert config is not None
        assert config.path == "/custom/gitleaks"
    finally:
        discover_tools()


# _get_wrapper_availability path fix


def test_tool_add_global_shows_unconfigured_wrapper(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "commands.json").write_text("{}")

    tc, repl = _make_tc(base_path=str(tmp_path))

    with (
        patch.object(
            tc, "_get_wrapper_availability", return_value=({"npm-audit"}, set())
        ),
        patch("builtins.input", return_value=""),
    ):
        tc._cmd_tool_add()

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert not any(
        "All available tools are already configured" in c for c in printed_calls
    )


def test_tool_add_project_shows_unconfigured_wrapper(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "myproject" / "config"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text("{}")
    (project_dir / "commands.json").write_text("{}")
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "commands.json").write_text("{}")

    tc, repl = _make_tc(base_path=str(tmp_path))

    with (
        patch.object(
            tc, "_get_wrapper_availability", return_value=({"npm-audit"}, set())
        ),
        patch("builtins.input", return_value=""),
    ):
        tc._cmd_tool_add_project("myproject")

    printed_calls = [str(c) for c in repl.console.print.call_args_list]
    assert not any(
        "All available tools are already configured at the project level" in c
        for c in printed_calls
    )


def test_discover_tools_no_project(tmp_path: Path) -> None:
    from application.tools.registry import discover_tools, tool_registry

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/gitleaks",
                }
            }
        )
    )

    try:
        discover_tools(str(tmp_path))
        config = tool_registry.get_tool_config("gitleaks")
        assert config is not None
        assert config.path == "/usr/bin/gitleaks"
    finally:
        discover_tools()

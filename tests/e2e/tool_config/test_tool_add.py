"""E2E tests for `tool add` and `tool add --project=<name>`."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.tool_config.conftest import (
    ALL_TOOLS_EXCEPT_NOIR,
    ALL_TOOLS_SEEDED,
    add_noir_project_wizard,
    add_noir_wizard,
    create_and_switch_project,
    seed_commands_json,
)

pytestmark = pytest.mark.e2e


def test_tool_add_local(tally_harness: TallyHarness) -> None:
    h = tally_harness
    add_noir_wizard(h)
    output = h.wait_for_prompt()
    assert "Tool added" in output

    list_output = h.run("tool list")
    assert "noir" in list_output


def test_tool_add_all_configured(tally_harness: TallyHarness) -> None:
    seed_commands_json(tally_harness.base_path, ALL_TOOLS_SEEDED)
    output = tally_harness.run("tool add")
    assert "All available tools are already configured" in output


def test_tool_add_by_number(tally_harness: TallyHarness) -> None:
    h = tally_harness
    seed_commands_json(h.base_path, ALL_TOOLS_EXCEPT_NOIR)

    h.send("tool add")
    h.expect("Enter tool name")
    h.send("1")

    assert h.child is not None
    idx = h.child.expect(
        ["Local binary found", "not found on PATH"],
        timeout=h.default_timeout,
    )
    if idx == 0:
        h.expect("Use this path")
        h.send("y")
    else:
        h.expect("Enter path manually")
        h.send("/fake/noir")

    output = h.wait_for_prompt()
    assert "Tool added" in output


def test_tool_add_invalid_selection(tally_harness: TallyHarness) -> None:
    h = tally_harness
    h.send("tool add")
    h.expect("Enter tool name")
    h.send("99")
    output = h.wait_for_prompt()
    assert "Invalid selection" in output


def test_tool_add_project_level(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_and_switch_project(h, name="ToolProj", company="Co")

    add_noir_project_wizard(h, "ToolProj")
    output = h.wait_for_prompt()
    assert "Tool added" in output

    list_output = h.run("tool list --project=ToolProj")
    assert "noir" in list_output

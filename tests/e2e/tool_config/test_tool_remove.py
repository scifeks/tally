"""E2E tests for `tool remove` and `tool remove --project=<name>`."""

from __future__ import annotations

import json

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.tool_config.conftest import (
    create_and_switch_project,
    seed_commands_json,
    seed_project_commands_json,
)

pytestmark = pytest.mark.local_only

_NOIR_LOCAL = {
    "type": "repo",
    "location": "local",
    "path": "/fake/noir",
}


def test_tool_remove_confirmed(tally_harness: TallyHarness) -> None:
    h = tally_harness
    seed_commands_json(h.base_path, {"noir": _NOIR_LOCAL})

    h.send("tool remove noir")
    h.expect("Remove tool")
    h.send("y")
    output = h.wait_for_prompt()

    assert "Tool removed" in output

    list_output = h.run("tool list")
    assert "No tools configured" in list_output


def test_tool_remove_cancelled(tally_harness: TallyHarness) -> None:
    h = tally_harness
    seed_commands_json(h.base_path, {"noir": _NOIR_LOCAL})

    h.send("tool remove noir")
    h.expect("Remove tool")
    h.send("N")
    output = h.wait_for_prompt()

    assert "Cancelled" in output

    cfg = h.base_path / "config" / "commands.json"
    data = json.loads(cfg.read_text())
    assert "noir" in data


def test_tool_remove_not_configured(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool remove nosuch")
    assert "Tool not configured" in output


def test_tool_remove_no_name(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool remove")
    assert "Usage" in output


def test_tool_remove_project_level(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_and_switch_project(h, name="RemProj", company="Co")
    seed_project_commands_json(h.base_path, "RemProj", {"noir": _NOIR_LOCAL})

    h.send("tool remove noir --project=RemProj")
    h.expect("Remove tool")
    h.send("y")
    output = h.wait_for_prompt()

    assert "Tool removed" in output

    list_output = h.run("tool list --project=RemProj")
    assert "No project-level tool overrides" in list_output


def test_tool_remove_project_not_configured(
    tally_harness: TallyHarness,
) -> None:
    h = tally_harness
    create_and_switch_project(h, name="RemProj2", company="Co")
    output = h.run("tool remove nosuch --project=RemProj2")
    assert "Tool not configured" in output

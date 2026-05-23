"""E2E tests for `tool edit` and `tool edit --project=<name>`."""

from __future__ import annotations

import json

import pytest

from tests.e2e.cli.harness import TallyHarness
from tests.e2e.cli.tool_config.conftest import (
    create_and_switch_project,
    seed_commands_json,
    seed_project_commands_json,
)

pytestmark = pytest.mark.e2e

_NOIR_LOCAL = {
    "type": "repo",
    "location": "local",
    "path": "/fake/noir",
}


def test_tool_edit_updates_config(tally_harness: TallyHarness) -> None:
    h = tally_harness
    seed_commands_json(h.base_path, {"noir": _NOIR_LOCAL})

    h.send("tool edit noir")
    h.expect("Enter new path")
    h.send("/updated/noir")
    output = h.wait_for_prompt()

    assert "Tool updated" in output

    cfg = h.base_path / "config" / "commands.json"
    data = json.loads(cfg.read_text())
    assert data["noir"]["path"] == "/updated/noir"


def test_tool_edit_not_configured(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool edit nosuch")
    assert "Tool not configured" in output


def test_tool_edit_no_name(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool edit")
    assert "Usage" in output


def test_tool_edit_project_level(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_and_switch_project(h, name="EditProj", company="Co")
    seed_project_commands_json(h.base_path, "EditProj", {"noir": _NOIR_LOCAL})

    h.send("tool edit noir --project=EditProj")
    h.expect("Enter new path")
    h.send("/updated/project/noir")
    output = h.wait_for_prompt()

    assert "Tool updated" in output

    cfg = h.base_path / "projects" / "EditProj" / "config" / "commands.json"
    data = json.loads(cfg.read_text())
    assert data["noir"]["path"] == "/updated/project/noir"


def test_tool_edit_project_not_configured(
    tally_harness: TallyHarness,
) -> None:
    h = tally_harness
    create_and_switch_project(h, name="EditProj2", company="Co")
    output = h.run("tool edit nosuch --project=EditProj2")
    assert "Tool not configured" in output

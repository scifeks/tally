"""Shared helpers for tool config e2e tests."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.project_lifecycle.conftest import create_project

# Minimal valid local CommandEntry for seeding commands.json
_LOCAL = {"type": "repo", "location": "local", "path": "/fake/tool"}

# All tool names derived from wrappers/local/ and wrappers/docker/
ALL_TOOL_NAMES: list[str] = sorted(
    [
        "composer-audit",
        "dalfox",
        "gitleaks",
        "katana",
        "noir",
        "npm-audit",
        "osv-scanner",
        "pip-audit",
        "semgrep",
        "xsstrike",
        "zap",
    ]
)

# Commands dict with every tool configured as a local tool
ALL_TOOLS_SEEDED: dict[str, dict] = {
    name: {"type": "repo", "location": "local", "path": f"/fake/{name}"}
    for name in ALL_TOOL_NAMES
}

# All tools except noir (used to force noir to be the only option)
ALL_TOOLS_EXCEPT_NOIR: dict[str, dict] = {
    name: entry for name, entry in ALL_TOOLS_SEEDED.items() if name != "noir"
}


def seed_commands_json(base_path: Path, tools: dict) -> None:
    """Write *tools* to config/commands.json under *base_path*."""
    path = base_path / "config" / "commands.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tools, indent=2))


def seed_project_commands_json(base_path: Path, project_name: str, tools: dict) -> None:
    """Write *tools* to projects/<name>/config/commands.json."""
    path = base_path / "projects" / project_name / "config" / "commands.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tools, indent=2))


def create_and_switch_project(
    h: TallyHarness,
    name: str = "TestProj",
    company: str = "TestCo",
) -> str:
    """Create a project and switch to it; return the project name."""
    create_project(h, name=name, company=company)
    h.run(f"project switch {name}")
    return name


def add_noir_wizard(h: TallyHarness) -> None:
    """Drive the tool-add wizard for noir (local-only tool).

    Handles both the "binary found" and "not found on PATH" branches.
    Caller should assert "Tool added" on the output from wait_for_prompt().
    """
    h.send("tool add")
    h.expect("Enter tool name")
    h.send("noir")
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


def add_noir_project_wizard(h: TallyHarness, project_name: str) -> None:
    """Drive tool add --project=<name> wizard for noir."""
    h.send(f"tool add --project={project_name}")
    h.expect("Enter tool name")
    h.send("noir")
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


@pytest.fixture()
def tally_harness_with_gitleaks(
    tmp_path: Path,
) -> Generator[TallyHarness]:
    """Isolated harness pre-seeded with a gitleaks local entry.

    Because commands.json is written before spawn(), discover_tools()
    registers gitleaks in the in-process registry on startup.
    """
    harness = TallyHarness(base_path=tmp_path)
    harness.setup()
    seed_commands_json(
        tmp_path,
        {
            "gitleaks": {
                "type": "repo",
                "location": "local",
                "path": "/fake/gitleaks",
            }
        },
    )
    harness.spawn()
    yield harness
    harness.teardown()

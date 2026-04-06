"""E2E tests for `tool list` and `tool list --project=<name>`."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.tool_config.conftest import create_and_switch_project

pytestmark = pytest.mark.local_only


def test_tool_list_empty(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool list")
    assert "No tools configured" in output


def test_tool_list_shows_configured_tools(
    tally_harness_with_gitleaks: TallyHarness,
) -> None:
    output = tally_harness_with_gitleaks.run("tool list")
    assert "gitleaks" in output


def test_tool_list_live(tally_harness_live: TallyHarness) -> None:
    output = tally_harness_live.run("tool list")
    assert "No tools configured" not in output


def test_tool_list_project_shows_overrides(
    tally_harness_live: TallyHarness,
) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    output = h.run("tool list --project=DVPA")
    assert "pip-audit" in output


def test_tool_list_project_empty(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_and_switch_project(h, name="EmptyTools", company="Co")
    output = h.run("tool list --project=EmptyTools")
    assert "No project-level tool overrides" in output


def test_tool_list_project_not_found(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_and_switch_project(h, name="RealProj", company="Co")
    output = h.run("tool list --project=NoSuch")
    assert "Project not found" in output

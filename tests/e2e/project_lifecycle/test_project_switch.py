"""E2E tests for the `project switch` command."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.local_only


def test_project_switch_valid(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="SwitchProj", company="Co")

    output = h.run("project switch SwitchProj")

    assert "Switched to project: SwitchProj" in output


def test_project_switch_nonexistent(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project switch NoSuchProject")

    assert "Project not found" in output


def test_project_switch_no_name(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project switch")

    assert "Usage" in output
    assert "project switch" in output

"""E2E tests for the `project delete` command."""

from __future__ import annotations

import pytest

from tests.e2e.cli.harness import TallyHarness
from tests.e2e.cli.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.e2e


def test_project_delete_confirmed(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="DelMe", company="Co")

    h.send("project delete DelMe")
    h.expect("Delete project")
    h.send("y")
    output = h.wait_for_prompt()

    assert "deleted" in output

    list_output = h.run("project list")
    assert "DelMe" not in list_output


def test_project_delete_clears_active(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="ActiveDel", company="Co")
    h.run("project switch ActiveDel")

    h.send("project delete ActiveDel")
    h.expect("Delete project")
    h.send("y")
    output = h.wait_for_prompt()

    assert "Active project cleared" in output


def test_project_delete_cancelled(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="KeepMe", company="Co")

    h.send("project delete KeepMe")
    h.expect("Delete project")
    h.send("N")
    output = h.wait_for_prompt()

    assert "Cancelled" in output

    list_output = h.run("project list")
    assert "KeepMe" in list_output


def test_project_delete_nonexistent(tally_harness: TallyHarness) -> None:
    h = tally_harness

    h.send("project delete NoSuch")
    h.expect("Delete project")
    h.send("y")
    output = h.wait_for_prompt()

    assert "Error" in output


def test_project_delete_no_name(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project delete")

    assert "Usage" in output

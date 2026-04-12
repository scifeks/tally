"""E2E tests for the `project list` command."""

from __future__ import annotations

from datetime import date

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.local_only


def test_project_list_empty(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project list")
    assert "No projects found" in output


def test_project_list_after_add(tally_harness: TallyHarness) -> None:
    create_project(tally_harness, name="ListProj", company="ListCo")

    output = tally_harness.run("project list")

    assert "ListProj" in output
    assert date.today().isoformat() in output
    assert "0" in output

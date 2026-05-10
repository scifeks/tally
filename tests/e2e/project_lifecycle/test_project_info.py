"""E2E tests for the `project info` command."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.e2e


def test_project_info_shows_details(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="InfoProj", company="InfoCo")
    h.run("project switch InfoProj")

    output = h.run("project info")

    assert "InfoProj" in output
    assert "Created:" in output
    assert "Repositories:" in output


def test_project_info_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project info")

    assert "No active project" in output

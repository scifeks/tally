"""E2E tests for run command error paths."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


def test_run_no_args(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("run")
    assert "Usage" in output


def test_run_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("run gitleaks")
    assert "No active project" in output


def test_run_unknown_tool(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    output = h.run("run nosuch")
    assert "Tool not found" in output

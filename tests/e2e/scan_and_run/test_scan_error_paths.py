"""E2E tests for scan command error paths."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.local_only


def test_scan_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("scan")
    assert "No active project" in output


def test_scan_unrecognized_flag(tally_harness: TallyHarness) -> None:
    create_project(tally_harness, name="FlagTest", company="Co")
    tally_harness.run("project switch FlagTest")
    output = tally_harness.run("scan --badarg=foo")
    assert "Unrecognized argument" in output


def test_scan_tool_and_skip_tools_mutually_exclusive(
    tally_harness: TallyHarness,
) -> None:
    create_project(tally_harness, name="MutexTest", company="Co")
    tally_harness.run("project switch MutexTest")
    output = tally_harness.run("scan --tool=gitleaks --skip-tools=semgrep")
    assert "mutually exclusive" in output


def test_scan_unknown_repo(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    output = h.run("scan --repo=nosuch")
    assert "Unknown repository" in output


def test_scan_unknown_tool(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    output = h.run("scan --tool=nosuch")
    assert "Unknown tool" in output


def test_scan_unknown_domain(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    output = h.run("scan --domain=nosuch")
    assert "Unknown domain" in output


def test_scan_unknown_skip_tool(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    output = h.run("scan --skip-tools=nosuch")
    assert "Unknown tool" in output

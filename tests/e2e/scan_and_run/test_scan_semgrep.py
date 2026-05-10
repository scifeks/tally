"""E2E tests for scan --tool=semgrep with SQLite assertions."""

from __future__ import annotations

import shutil

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.e2e

requires_semgrep = pytest.mark.skipif(
    shutil.which("semgrep") is None,
    reason="semgrep binary not installed",
)


@requires_semgrep
@pytest.mark.slow
@pytest.mark.skip(
    reason="Runs semgrep across all DVPA repos, too slow until synthetic "
    "test repos are in place"
)
def test_scan_semgrep_produces_findings(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    h.run("scan --tool=semgrep --yes", timeout=360)
    rows = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE tool='semgrep'",
    )
    assert rows[0]["n"] > 0

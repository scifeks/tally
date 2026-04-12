"""E2E tests for scan --skip-tools=<tool> execution."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


@pytest.mark.slow
def test_scan_skip_tools(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    h.run("scan --skip-tools=gitleaks --yes", timeout=300)

    run_rows = h.query_db("DVPA", "SELECT MAX(id) as last_run FROM runs")
    last_run_id = run_rows[0]["last_run"]
    assert last_run_id is not None

    # No gitleaks findings should have been created in this run.
    rows = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND tool = 'gitleaks'",
        (last_run_id,),
    )
    assert rows[0]["n"] == 0

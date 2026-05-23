"""E2E tests for scan --skip-tools=<tool> execution."""

from __future__ import annotations

import pytest

from tests.e2e.cli.harness import TallyHarness

pytestmark = pytest.mark.e2e


@pytest.mark.slow
@pytest.mark.skip(
    reason="Runs full scan minus gitleaks across all DVPA repos, too slow until "
    "synthetic test repos are in place"
)
def test_scan_skip_tools(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")

    pre = h.query_db("DVPA", "SELECT COALESCE(MAX(id), 0) as n FROM runs")
    pre_max = pre[0]["n"]

    h.run("scan --skip-tools=gitleaks --yes", timeout=600)

    run_rows = h.query_db(
        "DVPA",
        "SELECT MAX(id) as last_run FROM runs WHERE id > ?",
        (pre_max,),
    )
    last_run_id = run_rows[0]["last_run"]
    assert last_run_id is not None, "Scan did not create a run entry"

    # No gitleaks findings should have been created in this run.
    rows = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND tool = 'gitleaks'",
        (last_run_id,),
    )
    assert rows[0]["n"] == 0

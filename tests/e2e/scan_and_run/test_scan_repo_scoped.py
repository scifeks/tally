"""E2E tests for scan --repo=<repo> scoped execution."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


@pytest.mark.slow
def test_scan_repo_scoped(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")

    pre = h.query_db("DVPA", "SELECT COALESCE(MAX(id), 0) as n FROM runs")
    pre_max = pre[0]["n"]

    h.run("scan --repo=dvpwa --yes", timeout=1800)

    run_rows = h.query_db(
        "DVPA",
        "SELECT MAX(id) as last_run FROM runs WHERE id > ?",
        (pre_max,),
    )
    last_run_id = run_rows[0]["last_run"]
    assert last_run_id is not None, "Scan did not create a run entry"

    # All findings created in this run must be scoped to dvpwa.
    bad = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND repo != 'dvpwa'",
        (last_run_id,),
    )
    assert bad[0]["n"] == 0

    # At least one finding must exist for dvpwa.
    good = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND repo = 'dvpwa'",
        (last_run_id,),
    )
    assert good[0]["n"] > 0

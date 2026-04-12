"""E2E tests for scan --domain=<domain> scoped execution."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


@pytest.mark.slow
def test_scan_domain_code(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    h.run("scan --domain=code --yes", timeout=300)

    run_rows = h.query_db("DVPA", "SELECT MAX(id) as last_run FROM runs")
    last_run_id = run_rows[0]["last_run"]
    assert last_run_id is not None

    # All findings in this run must belong to the 'code' domain.
    bad = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND domain != 'code'",
        (last_run_id,),
    )
    assert bad[0]["n"] == 0

    # At least one finding must exist.
    good = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ?",
        (last_run_id,),
    )
    assert good[0]["n"] > 0

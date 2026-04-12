"""E2E tests for scan --domain=<domain> scoped execution."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


@pytest.mark.slow
@pytest.mark.skip(
    reason="Runs all code-domain tools across all DVPA repos — too slow until "
    "synthetic test repos are in place"
)
def test_scan_domain_code(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")

    pre = h.query_db("DVPA", "SELECT COALESCE(MAX(id), 0) as n FROM runs")
    pre_max = pre[0]["n"]

    h.run("scan --domain=code --yes", timeout=600)

    run_rows = h.query_db(
        "DVPA",
        "SELECT MAX(id) as last_run FROM runs WHERE id > ?",
        (pre_max,),
    )
    last_run_id = run_rows[0]["last_run"]
    assert last_run_id is not None, "Scan did not create a run entry"

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

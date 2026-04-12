"""E2E tests for scan --repo=<repo> scoped execution."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


@pytest.mark.slow
def test_scan_repo_scoped(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    h.run("scan --repo=php-goof --yes", timeout=300)

    run_rows = h.query_db("DVPA", "SELECT MAX(id) as last_run FROM runs")
    last_run_id = run_rows[0]["last_run"]
    assert last_run_id is not None

    # All findings created in this run must be scoped to php-goof.
    bad = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND repo != 'php-goof'",
        (last_run_id,),
    )
    assert bad[0]["n"] == 0

    # At least one finding must exist for php-goof.
    good = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE run_id = ? AND repo = 'php-goof'",
        (last_run_id,),
    )
    assert good[0]["n"] > 0

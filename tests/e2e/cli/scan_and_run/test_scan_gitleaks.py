"""E2E tests for scan --tool=gitleaks with SQLite assertions."""

from __future__ import annotations

import pytest

from tests.conftest import requires_gitleaks
from tests.e2e.cli.harness import TallyHarness

pytestmark = pytest.mark.e2e


@requires_gitleaks
@pytest.mark.slow
def test_scan_gitleaks_produces_findings(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")
    h.run("scan --tool=gitleaks --yes", timeout=120)
    rows = h.query_db(
        "DVPA",
        "SELECT COUNT(*) as n FROM findings WHERE tool='gitleaks'",
    )
    assert rows[0]["n"] > 0

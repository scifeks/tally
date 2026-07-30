"""E2E test: full Antares scan via Tally adapter.

Requires the Antares CLI binary and a running model endpoint.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


class TestAntaresScanE2E:
    @pytest.mark.skip(reason="Requires Antares CLI + model endpoint")
    def test_sweep_scan_produces_findings(self) -> None:
        pass

    @pytest.mark.skip(reason="Requires Antares CLI + model endpoint")
    def test_partial_results_on_worker_failure(self) -> None:
        pass

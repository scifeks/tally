"""Tests that a stored finding's service reaches the Finding entity."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.findings.normalization import NormalizedFinding
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository

pytestmark = pytest.mark.integration


class TestFindingServiceRead:
    def test_service_is_read_back_and_null_stays_none(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "tally.db")
        factory.init_schema()
        repo = FindingRepository(factory)
        repo.insert_findings(
            1,
            [
                NormalizedFinding({"tool": "semgrep", "service": "api"}, {}, "fp-1"),
                NormalizedFinding({"tool": "burp"}, {}, "fp-2"),
            ],
        )

        by_fingerprint = {f.fingerprint: f.service for f in repo.get_all_findings()}

        assert by_fingerprint == {"fp-1": "api", "fp-2": None}

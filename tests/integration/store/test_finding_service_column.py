"""Tests that insert_findings persists the service column."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.findings.normalization import NormalizedFinding
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository

pytestmark = pytest.mark.integration


class TestFindingServiceColumn:
    def test_service_is_written_and_defaults_to_null(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "tally.db")
        factory.init_schema()
        FindingRepository(factory).insert_findings(
            1,
            [
                NormalizedFinding({"tool": "semgrep", "service": "api"}, {}, "fp-1"),
                NormalizedFinding({"tool": "burp"}, {}, "fp-2"),
            ],
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT fingerprint, service FROM findings ORDER BY fingerprint"
            ).fetchall()
        assert [(r["fingerprint"], r["service"]) for r in rows] == [
            ("fp-1", "api"),
            ("fp-2", None),
        ]

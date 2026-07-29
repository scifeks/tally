"""Tests for enrichment fields column name validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.finding_helpers import normalize_test_findings

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _first_id(factory: ConnectionFactory) -> int:
    with factory.connect() as conn:
        return conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]


class TestEnrichmentFieldsValidation:
    def test_update_enrichment_fields_rejects_unknown_columns(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Unknown column names must raise ValueError."""
        run_id = run_repo.create_run({})
        repo.insert_findings(run_id, normalize_test_findings([{"tool": "semgrep"}]))
        fid = _first_id(factory)

        with pytest.raises(ValueError, match="Unknown column names"):
            repo.update_enrichment_fields(fid, {"injected_col": "value"}, {})

    def test_update_enrichment_fields_accepts_valid_columns(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Valid enrichment columns must be accepted."""
        run_id = run_repo.create_run({})
        repo.insert_findings(run_id, normalize_test_findings([{"tool": "semgrep"}]))
        fid = _first_id(factory)

        repo.update_enrichment_fields(
            fid, {"severity": 3, "confidence": "high"}, {"risk_type": "xss"}
        )

        row = repo.get_finding(fid)
        assert row is not None
        assert row.confidence == "high"

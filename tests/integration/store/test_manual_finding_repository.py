"""Integration tests for manual finding repository methods."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import (
    FindingRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


class TestInsertManualFinding:
    def test_inserts_and_returns_id(self, finding_repo: FindingRepository) -> None:
        columns = {
            "tool": "manual",
            "domain": "code",
            "segment": "sast",
            "severity": 1,
            "file": "src/app.py",
            "finding_type": json.dumps(["vulnerability"]),
            "cwe": json.dumps(["CWE-798"]),
            "status": "active",
        }
        meta = {"title": "Hardcoded secret", "notes": ""}
        fingerprint = "abc123"

        fid = finding_repo.insert_manual_finding(columns, meta, fingerprint)
        assert isinstance(fid, int)
        assert fid > 0

    def test_finding_retrievable_after_insert(
        self, finding_repo: FindingRepository
    ) -> None:
        columns = {
            "tool": "manual",
            "domain": "code",
            "segment": "sast",
            "severity": 1,
            "file": "src/app.py",
            "status": "active",
        }
        meta = {"title": "Test finding"}
        fid = finding_repo.insert_manual_finding(columns, meta, "fp-001")
        found = finding_repo.get_finding(fid)
        assert found is not None
        assert found.tool == "manual"
        assert found.segment == "sast"
        assert found.file == "src/app.py"

    def test_run_id_is_none(self, finding_repo: FindingRepository) -> None:
        columns = {
            "tool": "manual",
            "domain": "code",
            "segment": "sast",
            "severity": 2,
            "url": "https://example.com",
            "status": "active",
        }
        fid = finding_repo.insert_manual_finding(columns, {}, "fp-002")
        found = finding_repo.get_finding(fid)
        assert found is not None
        assert found.run_id is None


class TestDeleteFindingById:
    def test_deletes_existing_finding(self, finding_repo: FindingRepository) -> None:
        columns = {
            "tool": "manual",
            "domain": "code",
            "segment": "sast",
            "severity": 1,
            "file": "src/app.py",
            "status": "active",
        }
        fid = finding_repo.insert_manual_finding(columns, {}, "fp-del")
        finding_repo.delete_finding_by_id(fid)
        assert finding_repo.get_finding(fid) is None

    def test_delete_nonexistent_is_noop(self, finding_repo: FindingRepository) -> None:
        finding_repo.delete_finding_by_id(999999)

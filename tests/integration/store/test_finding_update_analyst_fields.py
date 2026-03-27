"""Tests for FindingRepository.update_analyst_fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository

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


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
) -> int:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, findings)
    return run_id


def _first_id(factory: ConnectionFactory) -> int:
    with factory.connect() as conn:
        return conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]


class TestUpdateAnalystFields:
    def test_update_analyst_fields_writes_meta_keys(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        result = repo.update_analyst_fields(
            fid,
            {"risk_type": "xss", "remediation": "escape output"},
        )

        assert result is True
        row = repo.get_finding(fid)
        assert row is not None
        meta = json.loads(row["meta"])
        assert meta["risk_type"] == "xss"
        assert meta["remediation"] == "escape output"
        assert row["triaged_by"] == "analyst_web"

    def test_update_analyst_fields_updates_named_columns(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        result = repo.update_analyst_fields(fid, {"severity": "critical"})

        assert result is True
        row = repo.get_finding(fid)
        assert row is not None
        assert row["severity"] == "critical"
        assert row["triaged_by"] == "analyst_web"

    def test_update_analyst_fields_returns_false_on_unknown_finding(
        self,
        repo: FindingRepository,
    ) -> None:
        result = repo.update_analyst_fields(99999, {"severity": "low"})
        assert result is False

    def test_update_analyst_fields_returns_true_on_success(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        result = repo.update_analyst_fields(fid, {"severity": "high"})

        assert result is True

    def test_update_analyst_fields_preserves_existing_meta_keys(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Meta keys not present in the update dict must survive unchanged."""
        _seed(
            run_repo,
            repo,
            [{"tool": "semgrep", "severity": "low", "extra_field": "keep_me"}],
        )
        fid = _first_id(factory)

        repo.update_analyst_fields(fid, {"risk_type": "sqli"})

        row = repo.get_finding(fid)
        assert row is not None
        meta = json.loads(row["meta"])
        assert meta["risk_type"] == "sqli"
        assert meta.get("extra_field") == "keep_me"

    def test_update_analyst_fields_sets_triaged_at(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "gitleaks", "severity": "medium"}])
        fid = _first_id(factory)

        repo.update_analyst_fields(fid, {"owasp_name": "A03:2021"})

        row = repo.get_finding(fid)
        assert row is not None
        assert row["triaged_at"] is not None

    def test_update_analyst_fields_handles_all_meta_keys(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """All five accepted meta keys must land in the meta blob."""
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "high"}])
        fid = _first_id(factory)

        repo.update_analyst_fields(
            fid,
            {
                "remediation": "sanitise input",
                "risk_type": "injection",
                "owasp_name": "A03:2021",
                "title": "SQL Injection",
                "tags": ["critical", "backend"],
            },
        )

        row = repo.get_finding(fid)
        assert row is not None
        meta = json.loads(row["meta"])
        assert meta["remediation"] == "sanitise input"
        assert meta["risk_type"] == "injection"
        assert meta["owasp_name"] == "A03:2021"
        assert meta["title"] == "SQL Injection"
        assert meta["tags"] == ["critical", "backend"]

    def test_update_analyst_fields_mixed_meta_and_column(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """A single call may update both a named column and a meta key."""
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        repo.update_analyst_fields(
            fid,
            {"severity": "high", "risk_type": "rce"},
        )

        row = repo.get_finding(fid)
        assert row is not None
        assert row["severity"] == "high"
        meta = json.loads(row["meta"])
        assert meta["risk_type"] == "rce"
        assert row["triaged_by"] == "analyst_web"

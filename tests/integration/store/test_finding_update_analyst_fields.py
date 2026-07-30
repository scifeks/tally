"""Tests for FindingRepository.update_analyst_fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.findings.normalization import split_analyst_fields
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


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
) -> int:
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))
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

        fields = {"risk_type": "xss", "remediation": "escape output"}
        cols, meta = split_analyst_fields(fields)
        result = repo.update_analyst_fields(fid, cols, meta)

        assert result is True
        row = repo.get_finding(fid)
        assert row is not None
        meta_result = row.meta
        assert meta_result["risk_type"] == "xss"
        assert meta_result["remediation"] == "escape output"
        assert row.triaged_by == "analyst_web"

    def test_update_analyst_fields_updates_named_columns(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        fields = {"severity": "critical"}
        cols, meta = split_analyst_fields(fields)
        result = repo.update_analyst_fields(fid, cols, meta)

        assert result is True
        row = repo.get_finding(fid)
        assert row is not None
        assert row.severity == "critical"
        assert row.triaged_by == "analyst_web"

    def test_update_analyst_fields_returns_false_on_unknown_finding(
        self,
        repo: FindingRepository,
    ) -> None:
        fields = {"severity": "low"}
        cols, meta = split_analyst_fields(fields)
        result = repo.update_analyst_fields(99999, cols, meta)
        assert result is False

    def test_update_analyst_fields_returns_true_on_success(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        fields = {"severity": "high"}
        cols, meta = split_analyst_fields(fields)
        result = repo.update_analyst_fields(fid, cols, meta)

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

        fields = {"risk_type": "sqli"}
        cols, meta = split_analyst_fields(fields)
        repo.update_analyst_fields(fid, cols, meta)

        row = repo.get_finding(fid)
        assert row is not None
        meta_result = row.meta
        assert meta_result["risk_type"] == "sqli"
        assert meta_result.get("extra_field") == "keep_me"

    def test_update_analyst_fields_sets_triaged_at(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "gitleaks", "severity": "medium"}])
        fid = _first_id(factory)

        fields = {"owasp_name": "A03:2021"}
        cols, meta = split_analyst_fields(fields)
        repo.update_analyst_fields(fid, cols, meta)

        row = repo.get_finding(fid)
        assert row is not None
        assert row.triaged_at is not None

    def test_update_analyst_fields_handles_all_meta_keys(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """All five accepted meta keys must land in the meta blob."""
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "high"}])
        fid = _first_id(factory)

        fields = {
            "remediation": "sanitize input",
            "risk_type": "injection",
            "owasp_name": "A03:2021",
            "title": "SQL Injection",
            "tags": ["critical", "backend"],
        }
        cols, meta = split_analyst_fields(fields)
        repo.update_analyst_fields(fid, cols, meta)

        row = repo.get_finding(fid)
        assert row is not None
        meta_result = row.meta
        assert meta_result["remediation"] == "sanitize input"
        assert meta_result["risk_type"] == "injection"
        assert meta_result["owasp_name"] == "A03:2021"
        assert meta_result["title"] == "SQL Injection"
        assert meta_result["tags"] == ["critical", "backend"]

    def test_update_analyst_fields_mixed_meta_and_column(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """A single call may update both a named column and a meta key."""
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        fields = {"severity": "high", "risk_type": "rce"}
        cols, meta = split_analyst_fields(fields)
        repo.update_analyst_fields(fid, cols, meta)

        row = repo.get_finding(fid)
        assert row is not None
        assert row.severity == "high"
        meta_result = row.meta
        assert meta_result["risk_type"] == "rce"
        assert row.triaged_by == "analyst_web"

    def test_update_analyst_fields_rejects_unknown_columns(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Unknown column names must raise ValueError."""
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        with pytest.raises(ValueError, match="Unknown column names"):
            repo.update_analyst_fields(fid, {"malicious_col": "value"}, {})

    def test_batch_update_analyst_fields_rejects_unknown_columns(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Batch update must reject unknown column names."""
        _seed(run_repo, repo, [{"tool": "semgrep", "severity": "low"}])
        fid = _first_id(factory)

        with pytest.raises(ValueError, match="Unknown column names"):
            repo.batch_update_analyst_fields([fid], {"injected_col": "value"})

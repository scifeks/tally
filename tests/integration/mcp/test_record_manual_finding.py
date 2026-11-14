"""Integration tests for McpIngestService.record_manual_finding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from application.mcp.finding_payload import FindingPayloadError
from application.mcp.ingest_service import McpIngestService, UnknownRepositoryError
from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import Repository
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def repo_repo(factory: ConnectionFactory) -> RepositoryRepository:
    return RepositoryRepository(factory)


@pytest.fixture()
def repo_id(repo_repo: RepositoryRepository, tmp_path: Path) -> int:
    return repo_repo.insert(
        Repository(
            name="api",
            path=str(tmp_path),
            services=[RepoService(name="default", type=["api"], languages=["python"])],
        )
    )


@pytest.fixture()
def service(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    repo_repo: RepositoryRepository,
) -> McpIngestService:
    return McpIngestService(
        finding_repo=finding_repo,
        run_repo=RunRepository(factory),
        repo_repo=repo_repo,
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "file": "src/db.py",
        "line_number": 42,
        "description": "SQL query built from user input via string concat.",
        "severity": "critical",
        "confidence": "confirmed",
        "cwe": ["CWE-89"],
        "finding_type": ["vulnerability"],
        "rule_id": "injection.sql",
        "meta": {
            "title": "SQL Injection in User Lookup",
            "owasp_name": "Injection",
            "remediation": "Use parameterized queries.",
        },
    }
    payload.update(overrides)
    return payload


class TestRecordManualFinding:
    @pytest.mark.parametrize(
        "status", ["active", "false_positive", "fixed", "wont_fix"]
    )
    def test_stores_reviewed_manual_finding_with_status(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_id: int,
        status: str,
    ) -> None:
        finding_id = service.record_manual_finding(
            _payload(), repo_name="api", status=status
        )

        finding = finding_repo.get_finding(finding_id)
        assert finding is not None
        assert finding.status == status
        assert finding.tool == "manual"
        assert finding.run_id is None
        assert finding.repo_id == repo_id
        assert finding.should_report is True
        assert finding.triaged_by is None
        assert finding.triaged_at is None

    def test_status_defaults_to_active(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_id: int,
    ) -> None:
        finding_id = service.record_manual_finding(_payload(), repo_name="api")

        finding = finding_repo.get_finding(finding_id)
        assert finding is not None
        assert finding.status == "active"

    @pytest.mark.parametrize(
        ("overrides", "expected_domain"),
        [
            ({}, "code"),
            ({"segment": "sca"}, "code"),
            ({"segment": "web", "file": None, "line_number": None}, "web"),
        ],
        ids=["default-sast", "sca", "web"],
    )
    def test_derives_domain_from_segment(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_id: int,
        overrides: dict[str, Any],
        expected_domain: str,
    ) -> None:
        payload = _payload(**overrides)
        payload = {k: v for k, v in payload.items() if v is not None}

        finding_id = service.record_manual_finding(payload, repo_name="api")

        finding = finding_repo.get_finding(finding_id)
        assert finding is not None
        assert finding.domain == expected_domain

    def test_rejects_invalid_status_listing_valid_values(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_id: int,
    ) -> None:
        with pytest.raises(FindingPayloadError) as exc_info:
            service.record_manual_finding(_payload(), repo_name="api", status="fp")

        assert str(exc_info.value) == (
            "status 'fp' is invalid; valid statuses: "
            "active, false_positive, fixed, wont_fix"
        )
        assert finding_repo.get_all_findings() == []

    def test_rejects_invalid_payload_without_inserting(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_id: int,
    ) -> None:
        payload = _payload()
        del payload["description"]

        with pytest.raises(FindingPayloadError):
            service.record_manual_finding(payload, repo_name="api")

        assert finding_repo.get_all_findings() == []

    @pytest.mark.parametrize("soft_deleted", [False, True], ids=["unknown", "deleted"])
    def test_rejects_inactive_repo_without_inserting(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_repo: RepositoryRepository,
        repo_id: int,
        soft_deleted: bool,
    ) -> None:
        if soft_deleted:
            repo_repo.soft_delete(repo_id)
            repo_name = "api"
        else:
            repo_name = "nope"

        with pytest.raises(UnknownRepositoryError) as exc_info:
            service.record_manual_finding(_payload(), repo_name=repo_name)

        assert str(exc_info.value) == (
            f"repository '{repo_name}' is not an active repository in this project"
        )
        assert finding_repo.get_all_findings() == []

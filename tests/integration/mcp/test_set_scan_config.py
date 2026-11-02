"""Tests for set_scan_config MCP tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.mcp.ingest_service import McpIngestService
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
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def service(
    finding_repo: FindingRepository, run_repo: RunRepository
) -> McpIngestService:
    return McpIngestService(finding_repo=finding_repo, run_repo=run_repo)


class TestSetScanConfig:
    def test_set_scan_config_persists_and_resolves(
        self, service: McpIngestService, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        result = service.set_scan_config(
            project=None,
            run_id=run_id,
            only=["scan-xss-stored", "scan-injection-sql"],
            exclude=None,
            adversarial_verification=True,
        )

        assert result["ok"] is True
        assert "tally-scan-xss-stored" in result["resolved_only_full_slugs"]
        assert "tally-scan-injection-sql" in result["resolved_only_full_slugs"]
        assert result["resolved_exclude_full_slugs"] == []

    def test_set_scan_config_rejects_both_only_and_exclude(
        self, service: McpIngestService, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        with pytest.raises(ValueError, match="mutually exclusive"):
            service.set_scan_config(
                project=None,
                run_id=run_id,
                only=["scan-xss-stored"],
                exclude=["scan-injection-sql"],
                adversarial_verification=False,
            )

    def test_set_scan_config_rejects_unknown_slug(
        self, service: McpIngestService, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        with pytest.raises(Exception, match="registered.*display slug"):
            service.set_scan_config(
                project=None,
                run_id=run_id,
                only=["scan-not-a-real-skill"],
                exclude=None,
                adversarial_verification=False,
            )

    def test_set_scan_config_with_exclude(
        self, service: McpIngestService, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        result = service.set_scan_config(
            project=None,
            run_id=run_id,
            only=None,
            exclude=["scan-xss-stored"],
            adversarial_verification=False,
        )

        assert result["ok"] is True
        assert result["resolved_only_full_slugs"] == []
        assert "tally-scan-xss-stored" in result["resolved_exclude_full_slugs"]

    def test_set_scan_config_persists_to_db(
        self,
        service: McpIngestService,
        run_repo: RunRepository,
        factory: ConnectionFactory,
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        service.set_scan_config(
            project=None,
            run_id=run_id,
            only=["scan-xss-stored"],
            exclude=None,
            adversarial_verification=True,
        )

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT only_full_slugs_json, exclude_full_slugs_json, "
                "adversarial_verification FROM scan_configs WHERE run_id = ?",
                (run_id,),
            ).fetchone()

        assert row is not None
        assert "tally-scan-xss-stored" in row["only_full_slugs_json"]
        assert row["adversarial_verification"] == 1

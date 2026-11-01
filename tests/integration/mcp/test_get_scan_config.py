"""Tests for get_scan_config MCP tool."""

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


class TestGetScanConfig:
    def test_get_scan_config_returns_unconfigured_when_absent(
        self, service: McpIngestService, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        result = service.get_scan_config(project=None, run_id=run_id)

        assert result == {
            "is_configured": False,
            "only": [],
            "exclude": [],
            "adversarial_verification": False,
        }

    def test_get_scan_config_returns_display_slugs(
        self, service: McpIngestService, run_repo: RunRepository
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

        result = service.get_scan_config(project=None, run_id=run_id)

        assert result["is_configured"] is True
        assert result["only"] == ["scan-xss-stored"]
        assert result["exclude"] == []
        assert result["adversarial_verification"] is True

    def test_get_scan_config_with_exclude(
        self, service: McpIngestService, run_repo: RunRepository
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
            only=None,
            exclude=["scan-injection-sql", "scan-xss-reflected"],
            adversarial_verification=False,
        )

        result = service.get_scan_config(project=None, run_id=run_id)

        assert result["is_configured"] is True
        assert result["only"] == []
        assert set(result["exclude"]) == {"scan-injection-sql", "scan-xss-reflected"}
        assert result["adversarial_verification"] is False

    def test_get_scan_config_preserves_multiple_only_slugs(
        self, service: McpIngestService, run_repo: RunRepository
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
            only=["scan-xss-stored", "scan-injection-sql", "scan-access-control-csrf"],
            exclude=None,
            adversarial_verification=True,
        )

        result = service.get_scan_config(project=None, run_id=run_id)

        assert result["is_configured"] is True
        assert set(result["only"]) == {
            "scan-xss-stored",
            "scan-injection-sql",
            "scan-access-control-csrf",
        }
        assert result["exclude"] == []
        assert result["adversarial_verification"] is True

    def test_get_scan_config_converts_full_slugs_to_display_slugs(
        self,
        service: McpIngestService,
        run_repo: RunRepository,
        factory: ConnectionFactory,
    ) -> None:
        from datetime import UTC, datetime

        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        with factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_configs (
                    run_id,
                    only_full_slugs_json,
                    exclude_full_slugs_json,
                    adversarial_verification,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    '["tally-scan-xss-stored", "tally-scan-injection-sql"]',
                    '["tally-scan-access-control-csrf"]',
                    True,
                    datetime.now(UTC).isoformat(),
                ),
            )

        result = service.get_scan_config(project=None, run_id=run_id)

        assert result["is_configured"] is True
        assert set(result["only"]) == {"scan-xss-stored", "scan-injection-sql"}
        assert result["exclude"] == ["scan-access-control-csrf"]
        assert result["adversarial_verification"] is True
        assert all("tally-" not in slug for slug in result["only"])
        assert all("tally-" not in slug for slug in result["exclude"])

    def test_get_scan_config_filters_stale_slugs_with_warning(
        self,
        service: McpIngestService,
        run_repo: RunRepository,
        factory: ConnectionFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from datetime import UTC, datetime

        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        with factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_configs (
                    run_id,
                    only_full_slugs_json,
                    exclude_full_slugs_json,
                    adversarial_verification,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    '["tally-scan-xss-stored", "tally-scan-nope-not-real"]',
                    "[]",
                    False,
                    datetime.now(UTC).isoformat(),
                ),
            )

        result = service.get_scan_config(project=None, run_id=run_id)

        assert result["is_configured"] is True
        assert result["only"] == ["scan-xss-stored"]
        assert "tally-scan-nope-not-real" not in result["only"]
        assert any(
            "Stale scan slug filtered from config" in rec.message
            and "tally-scan-nope-not-real" in rec.message
            for rec in caplog.records
            if rec.levelname == "WARNING"
        )

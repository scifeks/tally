"""Tests for McpIngestService.end_scan."""

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


class TestCreateScanRun:
    def test_returns_run_id(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.create_scan_run(project_id=1, repo_ids=["repo1"])

        assert isinstance(result, dict)
        assert "run_id" in result
        assert isinstance(result["run_id"], int)

    def test_creates_run_with_claude_tool(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.create_scan_run(project_id=1, repo_ids=["repo1"])

        run_id = result["run_id"]
        row = run_repo.get(run_id)
        assert row is not None
        assert row.tool_ids == ["claudecode"]

    def test_creates_run_with_llm_domain(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.create_scan_run(project_id=1, repo_ids=["repo1"])

        run_id = result["run_id"]
        row = run_repo.get(run_id)
        assert row is not None
        assert row.domains == ["llm"]

    def test_creates_run_with_skip_enrichment_true(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.create_scan_run(project_id=1, repo_ids=["repo1"])

        run_id = result["run_id"]
        row = run_repo.get(run_id)
        assert row is not None
        assert row.skip_enrichment is True

    def test_creates_run_with_running_status(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.create_scan_run(project_id=1, repo_ids=["repo1"])

        run_id = result["run_id"]
        row = run_repo.get(run_id)
        assert row is not None
        assert row.status == "running"


class TestEndScan:
    def test_marks_run_done(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.end_scan(project_id=1, run_id=run_id)

        assert result == {"status": "done"}
        row = run_repo.get(run_id)
        assert row is not None
        assert row.status == "done"

    def test_sets_finished_at(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        service.end_scan(project_id=1, run_id=run_id)

        row = run_repo.get(run_id)
        assert row is not None
        assert row.finished_at is not None

    def test_response_format(
        self, run_repo: RunRepository, finding_repo: FindingRepository
    ) -> None:
        run_id = run_repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.end_scan(project_id=1, run_id=run_id)

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "done"

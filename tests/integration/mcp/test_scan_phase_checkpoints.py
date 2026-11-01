"""Integration tests for scan phase checkpoint MCP tools."""

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
def run_id(run_repo: RunRepository) -> int:
    return run_repo.create(
        project_id=1,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
    )


def insert_scan_phase_execution(
    factory: ConnectionFactory,
    *,
    run_id: int,
    phase: str,
    status: str = "rate_limited",
    attempt_number: int | None = None,
) -> None:
    """Helper to insert a scan_phase_executions row."""
    with factory.connect() as conn:
        if attempt_number is None:
            row = conn.execute(
                "SELECT MAX(attempt_number) FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = ?",
                (run_id, phase),
            ).fetchone()
            attempt_number = (row[0] or 0) + 1
        conn.execute(
            "INSERT INTO scan_phase_executions"
            " (run_id, phase, attempt_number, status)"
            " VALUES (?, ?, ?, ?)",
            (run_id, phase, attempt_number, status),
        )


class TestMarkScanPhaseComplete:
    def test_mark_and_get_phase_status(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Mark a phase complete and verify get_scan_phase_status reflects it."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)

        result = service.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="recon",
            metadata={"manifest_path": "/tmp/foo.md"},
        )

        assert result["ok"] is True
        assert "execution_id" in result

        status = service.get_scan_phase_status(project=None, run_id=run_id)
        assert "recon" in status["completed_phases"]
        assert status["latest_execution_per_phase"]["recon"]["status"] == "completed"

    def test_multiple_marks_increment_attempt_number(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Multiple calls to mark_scan_phase_complete auto-increment attempt_number."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)

        r1 = service.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="domain:injection",
            status="rate_limited",
            usage_pool="plan",
        )
        assert r1["ok"] is True
        assert r1["attempt_number"] == 1

        r2 = service.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="domain:injection",
            status="completed",
            usage_pool="api",
        )
        assert r2["ok"] is True
        assert r2["attempt_number"] == 2

        r3 = service.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="domain:injection",
            status="failed",
        )
        assert r3["ok"] is True
        assert r3["attempt_number"] == 3

        status = service.get_scan_phase_status(project=None, run_id=run_id)
        inj = status["latest_execution_per_phase"]["domain:injection"]
        assert inj["status"] == "failed"
        assert inj["usage_pool"] is None
        assert inj["started_at"] is not None

    def test_metadata_persisted(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        factory: ConnectionFactory,
    ) -> None:
        """Metadata dict is persisted to metadata_json."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)

        service.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="xss:stored",
            metadata={"findings_count": 3, "manifest_url": "https://foo.com/manifest"},
        )

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = ?",
                (run_id, "xss:stored"),
            ).fetchone()

        assert row is not None
        import json

        meta = json.loads(row["metadata_json"])
        assert meta["findings_count"] == 3
        assert meta["manifest_url"] == "https://foo.com/manifest"


class TestMarkInProgressFailed:
    def test_flips_in_progress_to_failed_leaves_completed_untouched(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        factory: ConnectionFactory,
    ) -> None:
        """in_progress rows flip to failed; completed rows stay unchanged."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)

        # Seed one in_progress and one completed phase
        insert_scan_phase_execution(
            factory, run_id=run_id, phase="xss:stored", status="in_progress"
        )
        service.mark_scan_phase_complete(project=None, run_id=run_id, phase="recon")

        service.mark_in_progress_failed(run_id=run_id, error_class="rate_limit_plan")

        with factory.connect() as conn:
            xss_row = conn.execute(
                "SELECT status, error_class, finished_at"
                " FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = 'xss:stored'",
                (run_id,),
            ).fetchone()
            recon_row = conn.execute(
                "SELECT status, error_class"
                " FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = 'recon'",
                (run_id,),
            ).fetchone()

        assert xss_row["status"] == "failed"
        assert xss_row["error_class"] == "rate_limit_plan"
        assert xss_row["finished_at"] is not None

        assert recon_row["status"] == "completed"
        assert recon_row["error_class"] is None


class TestGetScanPhaseStatus:
    def test_empty_run_returns_empty_status(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Empty run returns empty completed_phases and latest_execution_per_phase."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        status = service.get_scan_phase_status(project=None, run_id=run_id)

        assert status["completed_phases"] == []
        assert status["latest_execution_per_phase"] == {}

    def test_multiple_phases_tracked(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Multiple distinct phases tracked correctly."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)

        service.mark_scan_phase_complete(project=None, run_id=run_id, phase="recon")
        service.mark_scan_phase_complete(
            project=None, run_id=run_id, phase="injection:sql"
        )

        status = service.get_scan_phase_status(project=None, run_id=run_id)

        latest = status["latest_execution_per_phase"]
        assert sorted(status["completed_phases"]) == [
            "injection:sql",
            "recon",
        ]
        assert "recon" in latest
        assert "injection:sql" in latest
        assert latest["recon"]["status"] == "completed"
        assert latest["injection:sql"]["status"] == "completed"

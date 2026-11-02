"""Tests for McpIngestService scan phase lifecycle events."""

from __future__ import annotations

from pathlib import Path

from application.mcp.ingest_service import McpIngestService
from domain.pipeline.scan_events import (
    PhaseCompleted,
    PhaseFailed,
    PhaseRateLimited,
    PhaseStarted,
    ScanEvent,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository


class _CapturingScanSink:
    def __init__(self) -> None:
        self.events: list[ScanEvent] = []

    def emit(self, event: ScanEvent) -> None:
        self.events.append(event)


def _make_service(
    db_path: Path,
    *,
    sink: _CapturingScanSink | None = None,
) -> McpIngestService:
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    return McpIngestService(
        finding_repo=FindingRepository(factory),
        run_repo=RunRepository(factory),
        scan_event_sink=sink,
    )


def _create_run(db_path: Path) -> int:
    """Insert a scan_runs row and return its id."""
    factory = ConnectionFactory(db_path)
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO scan_runs (project_id, status, created_at)"
            " VALUES (1, 'running', '2026-01-01T00:00:00')"
        )
        assert cur.lastrowid is not None
        return cur.lastrowid


class TestStartScanPhase:
    def test_writes_in_progress_row_and_emits_phase_started(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        result = svc.start_scan_phase(
            project=None, run_id=run_id, phase="recon", usage_pool="plan"
        )

        assert result["ok"] is True
        assert result["attempt_number"] == 1

        factory = ConnectionFactory(db)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scan_phase_executions WHERE id = ?",
                (result["execution_id"],),
            ).fetchone()
            assert row["status"] == "in_progress"
            assert row["attempt_number"] == 1
            assert row["usage_pool"] == "plan"
            assert row["finished_at"] is None

        assert len(sink.events) == 1
        evt = sink.events[0]
        assert isinstance(evt, PhaseStarted)
        assert evt.phase == "recon"
        assert evt.attempt_number == 1
        assert evt.usage_pool == "plan"

    def test_increments_attempt_number_on_retry(self, tmp_path: Path) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        svc.start_scan_phase(project=None, run_id=run_id, phase="recon")
        result2 = svc.start_scan_phase(project=None, run_id=run_id, phase="recon")

        assert result2["attempt_number"] == 2

        assert len(sink.events) == 2
        assert isinstance(sink.events[1], PhaseStarted)
        assert sink.events[1].attempt_number == 2


class TestStartThenComplete:
    def test_start_then_complete_reuses_attempt_row(self, tmp_path: Path) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        svc.start_scan_phase(
            project=None, run_id=run_id, phase="recon", usage_pool="plan"
        )
        svc.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="recon",
            status="completed",
            usage_pool="plan",
            metadata={"findings_count": 3},
        )

        factory = ConnectionFactory(db)
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT status, attempt_number FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = 'recon'"
                " ORDER BY attempt_number",
                (run_id,),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"
        assert rows[0]["attempt_number"] == 1

        started = [e for e in sink.events if isinstance(e, PhaseStarted)]
        completed = [e for e in sink.events if isinstance(e, PhaseCompleted)]
        assert len(started) == 1 and len(completed) == 1
        assert started[0].attempt_number == 1
        assert completed[0].attempt_number == 1


class TestMarkScanPhaseCompleteEvents:
    def test_emits_phase_completed_on_status_completed(self, tmp_path: Path) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        svc.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="domain:xss",
            status="completed",
            usage_pool="plan",
            metadata={"findings_count": 5},
        )

        completed_events = [e for e in sink.events if isinstance(e, PhaseCompleted)]
        assert len(completed_events) == 1
        evt = completed_events[0]
        assert evt.phase == "domain:xss"
        assert evt.attempt_number == 1
        assert evt.usage_pool == "plan"
        assert evt.findings_count == 5

    def test_emits_phase_failed_on_status_failed(self, tmp_path: Path) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        svc.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="domain:injection",
            status="failed",
            metadata={"error_class": "TRANSIENT_NETWORK"},
        )

        failed_events = [e for e in sink.events if isinstance(e, PhaseFailed)]
        assert len(failed_events) == 1
        evt = failed_events[0]
        assert evt.phase == "domain:injection"
        assert evt.error_class == "TRANSIENT_NETWORK"

    def test_emits_phase_rate_limited_on_status_rate_limited(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        svc.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="domain:xss",
            status="rate_limited",
            usage_pool="api",
        )

        rl_events = [e for e in sink.events if isinstance(e, PhaseRateLimited)]
        assert len(rl_events) == 1
        assert rl_events[0].usage_pool == "api"

    def test_without_sink_does_not_raise(self, tmp_path: Path) -> None:
        db = tmp_path / "findings.db"
        svc = _make_service(db, sink=None)
        run_id = _create_run(db)

        result = svc.mark_scan_phase_complete(
            project=None,
            run_id=run_id,
            phase="recon",
            status="completed",
        )
        assert result["ok"] is True


class TestMarkInProgressFailedEvents:
    def test_emits_phase_failed_for_each_flipped_row(self, tmp_path: Path) -> None:
        db = tmp_path / "findings.db"
        sink = _CapturingScanSink()
        svc = _make_service(db, sink=sink)
        run_id = _create_run(db)

        # Insert two in_progress rows and one completed row
        factory = ConnectionFactory(db)
        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO scan_phase_executions"
                " (run_id, phase, attempt_number, status, usage_pool, started_at)"
                " VALUES (?, 'domain:xss', 1, 'in_progress',"
                " 'plan', '2026-01-01T00:00:00')",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO scan_phase_executions"
                " (run_id, phase, attempt_number, status, usage_pool, started_at)"
                " VALUES (?, 'domain:injection', 2, 'in_progress',"
                " 'api', '2026-01-01T00:00:00')",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO scan_phase_executions"
                " (run_id, phase, attempt_number, status, usage_pool,"
                " started_at, finished_at)"
                " VALUES (?, 'recon', 1, 'completed', 'plan',"
                " '2026-01-01T00:00:00', '2026-01-01T00:01:00')",
                (run_id,),
            )

        svc.mark_in_progress_failed(run_id=run_id, error_class="RATE_LIMIT_PLAN")

        failed_events = [e for e in sink.events if isinstance(e, PhaseFailed)]
        assert len(failed_events) == 2

        by_phase = {e.phase: e for e in failed_events}
        assert set(by_phase) == {"domain:xss", "domain:injection"}

        xss_evt = by_phase["domain:xss"]
        assert xss_evt.attempt_number == 1
        assert xss_evt.usage_pool == "plan"
        assert xss_evt.error_class == "RATE_LIMIT_PLAN"
        assert xss_evt.run_id == run_id

        inj_evt = by_phase["domain:injection"]
        assert inj_evt.attempt_number == 2
        assert inj_evt.usage_pool == "api"
        assert inj_evt.error_class == "RATE_LIMIT_PLAN"
        assert inj_evt.run_id == run_id

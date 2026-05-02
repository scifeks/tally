"""Background report runner.

The HTTP generate route acquires the ``LockRegistry`` job slot
synchronously so a 409 returns immediately, then hands the lock off
to a daemon worker spawned here. The worker takes ownership of the
slot and releases it in its ``finally`` block.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.reporting.orchestrator import (
    ReportCancelled,
    ReportOverwriteDenied,
    ReportRequest,
    run_report,
)
from infrastructure.events.bus import EventBus
from web.adapters.event_bus_report_sink import EventBusReportSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
from web.adapters.report_run_registry import ReportRunRegistry

if TYPE_CHECKING:
    from application.ports.report_repository import ReportRepositoryPort

logger = logging.getLogger("tally.web.reports")


@dataclass(frozen=True)
class WebReportRequest:
    """Parsed POST body for /api/v1/projects/{id}/reports/generate."""

    format: str
    testing_type: str
    engagement_date: str | None
    output_path: str
    force_overwrite: bool
    company_name: str | None
    skip_triage: bool


def start_report_thread(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    report_id: int,
    request: WebReportRequest,
    holder_token: str,
    report_repo: ReportRepositoryPort,
    bus: EventBus,
    report_run_registry: ReportRunRegistry,
    retention_count: int,
    lock_registry: LockRegistry | None = None,
) -> threading.Thread:
    """Spawn a daemon worker thread to execute the report.

    The caller has ALREADY acquired the LockRegistry "report" slot under
    *holder_token*. The worker takes ownership and releases it in its
    ``finally`` block.
    """
    cancel_token = CancellationToken()
    report_run_registry.register(
        report_id=report_id,
        project_id=project_id,
        cancel_token=cancel_token,
    )

    thread = threading.Thread(
        target=_run_report,
        kwargs={
            "base_path": base_path,
            "project_name": project_name,
            "project_id": project_id,
            "report_id": report_id,
            "request": request,
            "holder_token": holder_token,
            "report_repo": report_repo,
            "bus": bus,
            "cancel_token": cancel_token,
            "lock_registry": lock_registry or get_registry(),
            "report_run_registry": report_run_registry,
            "retention_count": retention_count,
        },
        name=f"report-run-{report_id}",
        daemon=True,
    )
    thread.start()
    return thread


def _run_report(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    report_id: int,
    request: WebReportRequest,
    holder_token: str,
    report_repo: ReportRepositoryPort,
    bus: EventBus,
    cancel_token: CancellationToken,
    lock_registry: LockRegistry,
    report_run_registry: ReportRunRegistry,
    retention_count: int,
) -> None:
    sink = EventBusReportSink(bus)
    report_repo.set_status(report_id, "running")
    report_repo.set_started_at(report_id)

    orchestrator_request = ReportRequest(
        project=project_name,
        base_path=Path(base_path),
        format=request.format,
        output_path=Path(request.output_path),
        testing_type=request.testing_type,
        engagement_date=request.engagement_date,
        force_overwrite=request.force_overwrite,
        company_name_override=request.company_name,
        skip_triage=request.skip_triage,
        report_id=report_id,
        project_id=project_id,
    )

    try:
        try:
            output = run_report(
                orchestrator_request,
                prompt=NoApprovalPromptAdapter(),
                event_sink=sink,
                cancel_token=cancel_token,
            )
        except ReportCancelled:
            report_repo.set_status(report_id, "cancelled")
            report_repo.set_finished_at(report_id)
            logger.info("report run %d cancelled", report_id)
            return
        except ReportOverwriteDenied as exc:
            report_repo.set_status(report_id, "failed")
            report_repo.set_error(report_id, str(exc))
            report_repo.set_finished_at(report_id)
            logger.info("report run %d overwrite denied", report_id)
            return
        except Exception as exc:  # noqa: BLE001
            report_repo.set_status(report_id, "failed")
            report_repo.set_error(report_id, f"{type(exc).__name__}: {exc}")
            report_repo.set_finished_at(report_id)
            logger.exception("report run %d failed", report_id)
            return

        size = output.stat().st_size if output.exists() else 0
        report_repo.set_file_size(report_id, size)
        report_repo.set_status(report_id, "done")
        report_repo.set_finished_at(report_id)

        _enforce_retention(report_repo, project_id, retention_count)
    finally:
        report_run_registry.unregister(report_id)
        try:
            lock_registry.release_job("report", holder_token)
        except HolderMismatch:
            logger.warning("lock holder mismatch on report run %d release", report_id)
        except KeyError:
            logger.warning("report lock already released for run %d", report_id)


def _enforce_retention(
    repo: ReportRepositoryPort,
    project_id: int,
    keep: int,
) -> None:
    """Delete oldest non-pinned ``done`` rows beyond *keep*. Best-effort."""
    if keep <= 0:
        return
    try:
        rows = repo.select_for_retention(project_id, keep=keep)
    except Exception:  # noqa: BLE001
        logger.exception("retention sweep failed for project %d", project_id)
        return
    for row in rows:
        try:
            Path(row.filepath).unlink(missing_ok=True)
        except OSError:
            logger.warning("could not unlink %s during retention", row.filepath)
        try:
            repo.delete(row.id)
        except Exception:  # noqa: BLE001
            logger.exception("retention delete failed for report %d", row.id)

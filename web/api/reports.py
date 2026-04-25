"""Phase 7 — Report endpoints (history, latest, generate, cancel,
pin/delete, download, SSE).

Endpoint surface per ``docs/roadmap/ui-planning/API/endpoints.md §11``:

- ``GET    /api/v1/projects/{project_id}/reports``                  (history)
- ``GET    /api/v1/projects/{project_id}/reports/latest``           (latest)
- ``GET    /api/v1/projects/{project_id}/reports/events``           (SSE)
- ``POST   /api/v1/projects/{project_id}/reports/generate``         (start)
- ``GET    /api/v1/projects/{project_id}/reports/{report_id}/download``
- ``POST   /api/v1/projects/{project_id}/reports/{report_id}/pin``
- ``POST   /api/v1/projects/{project_id}/reports/{report_id}/cancel``
- ``DELETE /api/v1/projects/{project_id}/reports/{report_id}``

Route ordering: literal-segment routes (``.../latest``, ``.../events``,
``.../generate``) registered before parameterised routes
(``.../{report_id}``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from application.locking import JobBusy, get_registry
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.reports import (
    REPORT_STATUSES,
    ReportRepository,
    ReportRow,
)
from web.adapters.report_run_registry import get_report_run_registry
from web.api._errors import (
    Conflict,
    JobBusyError,
    NotFound,
    PathTraversal,
    ValidationError,
)
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    ReportCancelResponse,
    ReportGenerateRequest,
    ReportsListResponse,
    ReportSummary,
)
from web.reports.runner import WebReportRequest, start_report_thread

logger = logging.getLogger("tally.web.reports")


v1_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(row: dict) -> tuple[ReportRepository, ConnectionFactory]:
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    return ReportRepository(factory), factory


def _row_to_summary(report: ReportRow, project_id: int) -> ReportSummary:
    download_url: str | None = None
    if report.status == "done":
        download_url = f"/api/v1/projects/{project_id}/reports/{report.id}/download"
    return ReportSummary(
        id=report.id,
        project_id=report.project_id,
        scan_run_id=report.scan_run_id,
        format=report.format,
        filename=report.filename,
        status=report.status,
        pinned=report.retention_tier == "pinned",
        file_size_bytes=report.file_size_bytes,
        error=report.error,
        created_at=report.created_at,
        started_at=report.started_at,
        finished_at=report.finished_at,
        download_url=download_url,
    )


def _validate_status(status: str | None) -> None:
    if status is None:
        return
    if status not in REPORT_STATUSES:
        raise ValidationError(
            f"unknown report status {status!r}",
            details={"allowed": list(REPORT_STATUSES)},
        )


def _resolve_reports_dir(row: dict) -> Path:
    paths = ProjectPaths.from_registry_row(row)
    return paths.reports_dir.resolve()


def _ensure_within(base: Path, candidate: Path) -> None:
    """Raise PathTraversal if *candidate* escapes *base* after resolution."""
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise PathTraversal(
            f"could not resolve report path: {exc}",
            details={"path": str(candidate)},
        ) from exc
    if base != resolved and base not in resolved.parents:
        raise PathTraversal(
            "report path escapes the project's reports directory",
            details={"path": str(resolved), "base": str(base)},
        )


# ---------------------------------------------------------------------------
# Literal-segment routes first
# ---------------------------------------------------------------------------


@v1_router.get(
    "/{project_id}/reports/latest",
    response_model=ReportSummary | None,
)
async def get_latest_report(
    project_id: int,
    request: Request,
) -> ReportSummary | None:
    """Return the most recent ``done`` report for *project_id*, or ``null``."""
    row = _resolve_project(request, project_id)
    repo, _ = _make_repo(row)
    report = await asyncio.to_thread(repo.latest_for_project, project_id)
    if report is None:
        return None
    return _row_to_summary(report, project_id)


@v1_router.get("/{project_id}/reports/events")
async def reports_events(
    project_id: int,
    request: Request,
    report_id: int | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream emitting report lifecycle events for *project_id*."""
    row = _resolve_project(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("report")

    snapshot_event = await _build_snapshot(row, project_id, report_id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield format_sse_frame(snapshot_event)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item is EOS:
                    break
                payload = item.payload
                if payload.get("project_id") != project_id:
                    continue
                if report_id is not None and payload.get("report_id") != report_id:
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("report", sub_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v1_router.post(
    "/{project_id}/reports/generate",
    response_model=ReportSummary,
    status_code=202,
)
async def generate_report(
    project_id: int,
    request: Request,
    body: ReportGenerateRequest,
) -> ReportSummary:
    """Queue a new report in a worker thread.

    Returns 409 ``JOB_ALREADY_RUNNING`` if another report is in
    progress.
    """
    row = _resolve_project(request, project_id)
    project_name: str = row["name"]
    base_path: str = request.app.state.base_path

    repo, factory = _make_repo(row)

    paths = ProjectPaths.from_registry_row(row)
    reports_dir = paths.reports_dir
    reports_dir_resolved = reports_dir.resolve()

    if body.output_path:
        output_path = Path(body.output_path)
        if not output_path.is_absolute():
            output_path = (reports_dir / output_path).resolve()
        else:
            output_path = output_path.resolve()
        _ensure_within(reports_dir_resolved, output_path)
    else:
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        ext = "md" if body.format == "markdown" else body.format
        output_path = reports_dir_resolved / f"report_{ts}.{ext}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    lock_registry = get_registry()
    holder = f"report-web:{new_event_id()[:8]}"
    try:
        lock_registry.acquire_job("report", holder)
    except JobBusy as exc:
        raise JobBusyError("report", exc.current_holder) from exc

    try:
        config = ConfigManager(base_path).global_config
        retention_count = int(getattr(config, "report_retention_count", 10) or 0)
    except FileNotFoundError:
        retention_count = 10

    try:
        report_id = await asyncio.to_thread(
            repo.create,
            project_id=project_id,
            scan_run_id=None,
            format=body.format,
            filename=output_path.name,
            filepath=str(output_path),
        )
    except Exception:
        try:
            lock_registry.release_job("report", holder)
        except Exception:  # noqa: BLE001
            pass
        raise

    bus = request.app.state.event_bus
    web_request = WebReportRequest(
        format=body.format,
        testing_type=body.testing_type,
        engagement_date=body.engagement_date,
        output_path=str(output_path),
        force_overwrite=body.force_overwrite,
    )

    try:
        start_report_thread(
            base_path=base_path,
            project_name=project_name,
            project_id=project_id,
            report_id=report_id,
            request=web_request,
            holder_token=holder,
            factory=factory,
            bus=bus,
            report_run_registry=get_report_run_registry(),
            retention_count=retention_count,
            lock_registry=lock_registry,
        )
    except Exception:
        try:
            lock_registry.release_job("report", holder)
        except Exception:  # noqa: BLE001
            pass
        raise

    fresh = await asyncio.to_thread(repo.get, report_id)
    if fresh is None:
        raise NotFound(f"report {report_id} not found after creation")
    return _row_to_summary(fresh, project_id)


@v1_router.get(
    "/{project_id}/reports",
    response_model=ReportsListResponse,
)
async def list_reports(
    project_id: int,
    request: Request,
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ReportsListResponse:
    """Paginated report history for a project, newest-first."""
    row = _resolve_project(request, project_id)
    _validate_status(status)
    repo, _ = _make_repo(row)
    rows, total = await asyncio.to_thread(
        repo.list_for_project,
        project_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return ReportsListResponse(
        items=[_row_to_summary(r, project_id) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Parameterised routes
# ---------------------------------------------------------------------------


@v1_router.post(
    "/{project_id}/reports/{report_id}/cancel",
    response_model=ReportCancelResponse,
    status_code=202,
)
async def cancel_report(
    project_id: int,
    report_id: int,
    request: Request,
) -> ReportCancelResponse:
    """Request cancellation of an in-progress report run."""
    row = _resolve_project(request, project_id)
    repo, _ = _make_repo(row)

    handle = get_report_run_registry().get(report_id)
    if handle is None:
        report_row = await asyncio.to_thread(repo.get, report_id)
        if report_row is None or report_row.project_id != project_id:
            raise NotFound(f"report {report_id} not found")
        raise Conflict(
            f"report {report_id} is not in a cancellable state",
            code="REPORT_NOT_CANCELLABLE",
            details={"status": report_row.status},
        )

    if handle.project_id != project_id:
        raise NotFound(f"report {report_id} not found")

    handle.cancel_token.set()
    try:
        await asyncio.to_thread(repo.set_status, report_id, "cancelling")
    except Exception:  # noqa: BLE001
        logger.exception("failed to mark report %d cancelling", report_id)
    return ReportCancelResponse(id=report_id, status="cancelling")


@v1_router.post(
    "/{project_id}/reports/{report_id}/pin",
    status_code=204,
)
async def pin_report(
    project_id: int,
    report_id: int,
    request: Request,
) -> None:
    row = _resolve_project(request, project_id)
    repo, _ = _make_repo(row)
    report = await asyncio.to_thread(repo.get, report_id)
    if report is None or report.project_id != project_id:
        raise NotFound(f"report {report_id} not found")
    await asyncio.to_thread(repo.set_pinned, report_id, True)


@v1_router.delete(
    "/{project_id}/reports/{report_id}",
    status_code=204,
)
async def delete_report(
    project_id: int,
    report_id: int,
    request: Request,
) -> None:
    row = _resolve_project(request, project_id)
    repo, _ = _make_repo(row)
    report = await asyncio.to_thread(repo.get, report_id)
    if report is None or report.project_id != project_id:
        raise NotFound(f"report {report_id} not found")
    if report.retention_tier == "pinned":
        raise Conflict(
            f"report {report_id} is pinned; unpin before deleting",
            code="REPORT_PINNED",
            details={"retention_tier": "pinned"},
        )

    reports_dir = _resolve_reports_dir(row)
    candidate = Path(report.filepath)
    try:
        _ensure_within(reports_dir, candidate)
        candidate.resolve().unlink(missing_ok=True)
    except PathTraversal:
        logger.warning(
            "skipping unlink for report %d: path %s outside %s",
            report_id,
            report.filepath,
            reports_dir,
        )
    except OSError:
        logger.exception("could not unlink %s", report.filepath)
    await asyncio.to_thread(repo.delete, report_id)


@v1_router.get("/{project_id}/reports/{report_id}/download")
async def download_report(
    project_id: int,
    report_id: int,
    request: Request,
) -> FileResponse:
    """Stream the report file with server-side path-traversal validation."""
    row = _resolve_project(request, project_id)
    repo, _ = _make_repo(row)
    report = await asyncio.to_thread(repo.get, report_id)
    if report is None or report.project_id != project_id:
        raise NotFound(f"report {report_id} not found")
    if report.status != "done":
        raise Conflict(
            f"report {report_id} is not ready",
            code="REPORT_NOT_READY",
            details={"status": report.status},
        )

    reports_dir = _resolve_reports_dir(row)
    candidate = Path(report.filepath)
    _ensure_within(reports_dir, candidate)

    resolved = candidate.resolve()
    if not resolved.exists():
        raise NotFound(f"report file missing: {report.filename}")

    media_type = _media_type_for(report.format)
    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        filename=report.filename,
    )


def _media_type_for(fmt: str) -> str:
    return {
        "pdf": "application/pdf",
        "markdown": "text/markdown",
        "html": "text/html",
        "json": "application/json",
    }.get(fmt, "application/octet-stream")


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------


async def _build_snapshot(
    row: dict,
    project_id: int,
    report_id: int | None,
) -> BusEvent:
    """Build the on-connect ``snapshot`` BusEvent for a report SSE stream."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "report_id": report_id,
    }
    if report_id is not None:
        repo, _ = _make_repo(row)
        report = await asyncio.to_thread(repo.get, report_id)
        if report is not None and report.project_id == project_id:
            payload.update(
                status=report.status,
                format=report.format,
                filename=report.filename,
                file_size_bytes=report.file_size_bytes,
                started_at=report.started_at,
                finished_at=report.finished_at,
                error=report.error,
            )
    else:
        active = get_report_run_registry().list_for_project(project_id)
        payload["active_report_ids"] = [h.report_id for h in active]

    return BusEvent(
        event_id=new_event_id(),
        job_id="report",
        stream="report",
        event_type="snapshot",
        payload=payload,
        ts=datetime.now(UTC),
    )

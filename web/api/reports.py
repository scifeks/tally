"""Report and draft HTTP endpoints.

Route ordering: literal-segment routes (``.../latest``, ``.../events``,
``.../generate``) are registered before parameterized routes
(``.../{report_id}``) so Starlette does not shadow them.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from application.locking import JobBusy, get_registry
from application.reporting.draft_run_registry import get_draft_run_registry
from application.reporting.drafts import SECTION_REGISTRY
from application.reporting.reports_service import (
    ReportsService,
    UnknownSectionError,
)
from core.project_paths import ProjectPaths
from domain.pipeline.bus_event import EOS, BusEvent, new_event_id
from domain.projects.entry import ProjectRow
from domain.reports.entry import REPORT_STATUSES, ReportRow
from factories.persistence import ProjectNotFound, create_reports_service
from web.adapters.event_bus_draft_sink import EventBusDraftSink
from web.adapters.event_bus_report_update_sink import EventBusReportUpdateSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
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
    ReportPatchRequest,
    ReportsListResponse,
    ReportSummary,
)
from web.reports.runner import WebReportRequest, start_report_thread
from web.sse import format_sse_frame

logger = logging.getLogger("tally.web.reports")


v1_router = APIRouter()


def _service(request: Request, project_id: int) -> ReportsService:
    """Build a ReportsService for *project_id* or raise 404."""
    try:
        return create_reports_service(request.app.state.project_registry, project_id)
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


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
        display_name=report.display_name,
        notes=report.notes,
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


def _resolve_reports_dir(row: ProjectRow) -> Path:
    paths = ProjectPaths.from_registry_row(row)
    return paths.reports_dir.resolve()


def _build_draft_snapshot(project_id: int, section: str | None) -> BusEvent:
    active = get_draft_run_registry().get_for_project(project_id)
    payload: dict[str, Any] = {
        "project_id": project_id,
        "in_flight": [h.section for h in active],
    }
    if section is not None:
        payload["section"] = section
    return BusEvent(
        event_id=new_event_id(),
        job_id="report",
        stream="report_draft",
        event_type="snapshot",
        payload=payload,
        ts=datetime.now(UTC),
    )


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


# Literal-segment routes first


@v1_router.get(
    "/{project_id}/reports/latest",
    response_model=ReportSummary | None,
)
async def get_latest_report(
    project_id: int,
    request: Request,
) -> ReportSummary | None:
    """Return the most recent ``done`` report for *project_id*, or ``null``."""
    service = _service(request, project_id)
    report = await asyncio.to_thread(service.report_repo.latest_for_project, project_id)
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
    service = _service(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("report")

    snapshot_event = await _build_snapshot(service, project_id, report_id)

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
    project_name: str = row.name
    base_path: str = request.app.state.base_path

    service = _service(request, project_id)
    repo = service.report_repo

    paths = ProjectPaths.from_registry_row(row)
    reports_dir = paths.reports_dir

    output_path = ReportsService.resolve_output_path(
        body.output_path, body.format, reports_dir
    )
    if body.output_path:
        _ensure_within(reports_dir.resolve(), output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lock_registry = get_registry()
    holder = f"report-web:{new_event_id()[:8]}"
    try:
        lock_registry.acquire_job("report", holder)
    except JobBusy as exc:
        raise JobBusyError("report", exc.current_holder) from exc

    retention_count = ReportsService.get_retention_count(base_path)

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
        company_name=body.company_name,
        skip_triage=body.skip_triage,
    )

    try:
        start_report_thread(
            base_path=base_path,
            project_name=project_name,
            project_id=project_id,
            report_id=report_id,
            request=web_request,
            holder_token=holder,
            report_repo=repo,
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
    _validate_status(status)
    service = _service(request, project_id)
    rows, total = await asyncio.to_thread(
        service.report_repo.list_for_project,
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


# Draft routes (literal-segment, registered before /{report_id})

_DRAFT_MIME_ALLOWLIST = frozenset(
    {
        "text/markdown",
        "text/plain",
        "application/octet-stream",
    }
)
_DRAFT_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


class _DraftStartRequest(BaseModel):
    sections: list[str]
    force: bool = False
    skip_triage: bool = False


@v1_router.get("/{project_id}/reports/drafts")
async def list_drafts(
    project_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return one entry per section; absent rows report as ``not_generated``."""
    service = _service(request, project_id)
    summaries = await asyncio.to_thread(
        lambda: [service.get_section_summary(s) for s in SECTION_REGISTRY]
    )
    return {"drafts": [dataclasses.asdict(s) for s in summaries]}


@v1_router.post(
    "/{project_id}/reports/drafts",
    status_code=202,
)
async def start_drafts(
    project_id: int,
    request: Request,
    body: _DraftStartRequest,
) -> dict[str, Any]:
    """Queue sequential draft generation for one or more sections.

    Returns 409 if a report or draft batch is already in progress,
    or 422 if ``sections`` is empty, contains duplicates, or names a
    section not in the registry.
    """
    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    sink = EventBusDraftSink(request.app.state.event_bus)
    base_path = request.app.state.base_path

    def _llm_preflight() -> None:
        from infrastructure.llm.factory import get_llm_provider

        get_llm_provider("report", base_path)

    try:
        handle = await asyncio.to_thread(
            service.start_drafts,
            sections=body.sections,
            force=body.force,
            skip_triage=body.skip_triage,
            base_path=base_path,
            project_id=project_id,
            project_name=row.name,
            prompt=NoApprovalPromptAdapter(),
            event_sink=sink,
            preflight=_llm_preflight,
        )
    except UnknownSectionError as exc:
        raise ValidationError(
            str(exc), details={"allowed": list(SECTION_REGISTRY)}
        ) from exc
    except JobBusy as exc:
        raise JobBusyError("report", exc.current_holder) from exc
    except ValueError as exc:
        raise ValidationError(str(exc), details={}) from exc

    return {
        "drafts": [
            {
                "section": section,
                "status": "generating" if i == 0 else "queued",
            }
            for i, section in enumerate(handle.sections)
        ]
    }


@v1_router.get("/{project_id}/reports/drafts/events")
async def draft_events(
    project_id: int,
    request: Request,
    section: str | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream emitting draft lifecycle events for *project_id*."""
    _resolve_project(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("report_draft")

    snapshot = _build_draft_snapshot(project_id, section)

    async def stream() -> AsyncIterator[str]:
        try:
            yield format_sse_frame(snapshot)
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
                if section is not None and payload.get("section") != section:
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("report_draft", sub_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v1_router.post("/{project_id}/reports/drafts/upload")
async def upload_draft(
    project_id: int,
    request: Request,
    section: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Accept a Markdown upload and mark the section ``reviewed``."""
    if section not in SECTION_REGISTRY:
        raise ValidationError(
            f"unknown section {section!r}",
            details={"allowed": list(SECTION_REGISTRY)},
        )
    mime = file.content_type or "application/octet-stream"
    if mime not in _DRAFT_MIME_ALLOWLIST:
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": mime},
        )
    raw = await file.read(_DRAFT_MAX_BYTES + 1)
    if len(raw) > _DRAFT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="draft file exceeds 1 MiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            "draft file is not valid UTF-8", details={"error": str(exc)}
        ) from exc
    if "\x00" in text:
        raise ValidationError("draft file contains null bytes", details={})

    service = _service(request, project_id)
    await asyncio.to_thread(service.write_draft, section, text)

    original_filename = file.filename or f"{section}.md"
    now = datetime.now(UTC).isoformat()
    await asyncio.to_thread(
        service.draft_repo.mark_reviewed, section, original_filename, now
    )

    return {
        "section": section,
        "status": "reviewed",
        "uploaded_filename": original_filename,
        "word_count": len(text.split()),
    }


@v1_router.get("/{project_id}/reports/drafts/{section}/download")
async def download_draft(
    project_id: int,
    section: str,
    request: Request,
) -> Response:
    """Return the draft markdown for *section* as an attachment."""
    if section not in SECTION_REGISTRY:
        raise ValidationError(
            f"unknown section {section!r}",
            details={"allowed": list(SECTION_REGISTRY)},
        )
    service = _service(request, project_id)
    record = await asyncio.to_thread(service.draft_repo.get, section)
    if record is None:
        raise NotFound(f"draft {section!r} not found")

    text = await asyncio.to_thread(service.read_draft, section)
    if text is None:
        raise NotFound(f"draft file missing for section {section!r}")

    return Response(
        content=text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{section}.md"'},
    )


@v1_router.delete(
    "/{project_id}/reports/drafts/{section}",
    status_code=204,
)
async def delete_draft(
    project_id: int,
    section: str,
    request: Request,
) -> None:
    """Delete a draft section. Idempotent: 204 even if not present."""
    if section not in SECTION_REGISTRY:
        raise ValidationError(
            f"unknown section {section!r}",
            details={"allowed": list(SECTION_REGISTRY)},
        )
    service = _service(request, project_id)
    await asyncio.to_thread(service.delete_draft_file, section)
    await asyncio.to_thread(service.draft_repo.delete, section)


# Parameterized routes


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
    service = _service(request, project_id)
    repo = service.report_repo

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
    service = _service(request, project_id)
    repo = service.report_repo
    report = await asyncio.to_thread(repo.get, report_id)
    if report is None or report.project_id != project_id:
        raise NotFound(f"report {report_id} not found")
    await asyncio.to_thread(repo.set_pinned, report_id, True)


@v1_router.patch(
    "/{project_id}/reports/{report_id}",
    response_model=ReportSummary,
)
async def update_report_metadata(
    project_id: int,
    report_id: int,
    request: Request,
    body: ReportPatchRequest,
) -> ReportSummary:
    sink = EventBusReportUpdateSink(request.app.state.event_bus)
    service = create_reports_service(
        request.app.state.project_registry,
        project_id,
        report_update_sink=sink,
    )
    row = await asyncio.to_thread(
        service.update_report_metadata,
        report_id,
        project_id,
        display_name=body.display_name,
        notes=body.notes,
    )
    if row is None:
        raise NotFound(f"report {report_id} not found")
    return _row_to_summary(row, project_id)


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
    service = _service(request, project_id)
    repo = service.report_repo
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
    service = _service(request, project_id)
    report = await asyncio.to_thread(service.report_repo.get, report_id)
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


# Snapshot helper


async def _build_snapshot(
    service: ReportsService,
    project_id: int,
    report_id: int | None,
) -> BusEvent:
    """Build the on-connect ``snapshot`` BusEvent for a report SSE stream."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "report_id": report_id,
    }
    if report_id is not None:
        report = await asyncio.to_thread(service.report_repo.get, report_id)
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

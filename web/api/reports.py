"""Report and draft HTTP endpoints.

Route ordering: literal-segment routes (``.../latest``, ``.../events``,
``.../generate``) are registered before parameterized routes
(``.../{report_id}``) so Starlette does not shadow them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from application.locking import JobBusy, get_registry
from application.reporting.drafts import SECTION_REGISTRY
from application.reporting.reports_service import ProjectNotFound, ReportsService
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from domain.projects.entry import ProjectRow
from domain.reports.entry import REPORT_STATUSES, DraftRow, ReportRow
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from web.adapters.draft_run_registry import get_draft_run_registry
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
from web.reports.draft_runner import WebDraftRequest, start_draft_thread
from web.reports.runner import WebReportRequest, start_report_thread

logger = logging.getLogger("tally.web.reports")


v1_router = APIRouter()


# Helpers


def _service(request: Request, project_id: int) -> ReportsService:
    """Build a ReportsService for *project_id* or raise 404."""
    try:
        return ReportsService.for_project(
            request.app.state.project_registry, project_id
        )
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
        "active_sections": [h.section for h in active],
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
    section: str
    force: bool = False


def _resolve_drafts_dir(row: ProjectRow) -> Path:
    paths = ProjectPaths.from_registry_row(row)
    return paths.reports_draft_dir.resolve()


def _draft_section_summary(
    section: str,
    record: DraftRow | None,
    draft_dir: Path,
) -> dict[str, Any]:
    status = record.status if record else "not_generated"
    path = draft_dir / f"{section}.md"
    word_count: int | None = None
    preview: str | None = None
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            word_count = len(text.split())
            preview = text[:200]
        except OSError:
            pass
    return {
        "section": section,
        "status": status,
        "generated_at": record.generated_at if record else None,
        "reviewed_at": record.reviewed_at if record else None,
        "original_filename": record.original_filename if record else None,
        "word_count": word_count,
        "preview": preview,
    }


@v1_router.get("/{project_id}/reports/drafts")
async def list_drafts(
    project_id: int,
    request: Request,
) -> list[dict[str, Any]]:
    """Return one entry per section; absent rows report as ``not_generated``."""
    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    records = await asyncio.to_thread(service.draft_repo.list_all)
    draft_dir = _resolve_drafts_dir(row)
    by_section = {r.section: r for r in records}
    return [
        _draft_section_summary(s, by_section.get(s), draft_dir)
        for s in SECTION_REGISTRY
    ]


@v1_router.post(
    "/{project_id}/reports/drafts",
    status_code=202,
)
async def start_draft(
    project_id: int,
    request: Request,
    body: _DraftStartRequest,
) -> dict[str, Any]:
    """Queue draft generation for *section*.

    Returns 409 if any report or draft is already in progress,
    or 422 if *section* is not in the registry.
    """
    if body.section not in SECTION_REGISTRY:
        raise ValidationError(
            f"unknown section {body.section!r}",
            details={"allowed": list(SECTION_REGISTRY)},
        )
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path

    lock_registry = get_registry()
    holder = f"draft-web:{new_event_id()[:8]}"
    try:
        lock_registry.acquire_job("report", holder)
    except JobBusy as exc:
        raise JobBusyError("report", exc.current_holder) from exc

    service = _service(request, project_id)
    web_req = WebDraftRequest(section=body.section, force_overwrite=body.force)
    try:
        start_draft_thread(
            base_path=base_path,
            project_name=row.name,
            project_id=project_id,
            request=web_req,
            holder_token=holder,
            draft_repo=service.draft_repo,
            bus=request.app.state.event_bus,
            draft_run_registry=get_draft_run_registry(),
            lock_registry=lock_registry,
        )
    except Exception:
        try:
            lock_registry.release_job("report", holder)
        except Exception:  # noqa: BLE001
            pass
        raise

    return {"section": body.section, "status": "generating"}


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

    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    draft_dir = _resolve_drafts_dir(row)
    draft_dir.mkdir(parents=True, exist_ok=True)
    out = draft_dir / f"{section}.md"
    await asyncio.to_thread(out.write_text, text, "utf-8")

    original_filename = file.filename or f"{section}.md"
    now = datetime.now(UTC).isoformat()
    await asyncio.to_thread(
        service.draft_repo.mark_reviewed, section, original_filename, now
    )

    return {
        "section": section,
        "status": "reviewed",
        "original_filename": original_filename,
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
    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    record = await asyncio.to_thread(service.draft_repo.get, section)
    if record is None:
        raise NotFound(f"draft {section!r} not found")

    draft_dir = _resolve_drafts_dir(row)
    candidate = draft_dir / f"{section}.md"
    _ensure_within(draft_dir, candidate)

    if not candidate.exists():
        raise NotFound(f"draft file missing for section {section!r}")

    text = await asyncio.to_thread(candidate.read_text, "utf-8")
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
    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    draft_dir = _resolve_drafts_dir(row)
    candidate = draft_dir / f"{section}.md"
    try:
        _ensure_within(draft_dir, candidate)
        candidate.resolve().unlink(missing_ok=True)
    except PathTraversal:
        logger.warning("skipping unlink for draft %r: path outside draft dir", section)
    except OSError:
        logger.exception("could not unlink draft %s", candidate)
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

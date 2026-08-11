"""Scan lifecycle endpoints: config, start, history, detail,
cancel, and SSE event stream."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.locking import JobBusy
from application.project.repositories_service import ProjectRepositoriesService
from application.scans.scans_service import (
    ScanNotCancellable,
    ScanNotFound,
    ScansService,
    ScanValidationError,
)
from application.tools.registry import discover_tools
from core.project_paths import ProjectPaths
from domain.pipeline.bus_event import EOS, BusEvent, new_event_id
from domain.scans.entry import ScanRunRow, ToolRunRow
from domain.tools.scan_types import SEGMENT_ORDER
from factories.persistence import (
    ProjectNotFound,
    create_arg_profiles_repo,
    create_finding_repo,
    create_overrides_repo,
    create_repo_repo,
    create_scan_repos,
    create_scans_service,
    create_url_finding_repo,
)
from factories.scanning import create_git_diff, get_scan_service
from web.adapters.event_bus_scan_sink import EventBusScanSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
from web.api._errors import (
    Conflict,
    JobBusyError,
    NotFound,
)
from web.api._errors import (
    ValidationError as ApiValidationError,
)
from web.api._project_resolver import _resolve_project
from web.api._scan_run_summary import scan_run_to_summary
from web.api.schemas import (
    ScanCancelAllResponse,
    ScanCancelResponse,
    ScanConfigRepo,
    ScanConfigResponse,
    ScanConfigTool,
    ScanDetailResponse,
    ScanProgressResponse,
    ScanRunSummary,
    ScansListResponse,
    ScanStartRequest,
    ToolRunItem,
    ToolRunsSummary,
)
from web.sse import format_sse_frame

logger = logging.getLogger("tally.web.scans")


# All routes are project-scoped under /api/v1/projects/...
v1_router = APIRouter()


def _service(request: Request, project_id: int) -> ScansService:
    """Build a ScansService for *project_id* or raise 404."""
    try:
        return create_scans_service(request.app.state.project_registry, project_id)
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _tool_run_to_item(row: ToolRunRow) -> ToolRunItem:
    duration: float | None = None
    if row.started_at and row.finished_at:
        try:
            start = datetime.fromisoformat(row.started_at)
            end = datetime.fromisoformat(row.finished_at)
            duration = (end - start).total_seconds()
        except ValueError:
            duration = None
    return ToolRunItem(
        id=row.id,
        run_id=row.run_id,
        tool=row.tool,
        repo=row.repo,
        domain=row.domain,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration=duration,
        findings_count=row.findings_count,
        enriched_count=row.enriched_count,
        total_to_enrich=row.total_to_enrich,
        exit_code=row.exit_code,
        skip_reason=row.skip_reason,
    )


def _validation_error_to_envelope(exc: ScanValidationError) -> dict:
    return {"fields": [{"field": fe.field, "issue": fe.issue} for fe in exc.fields]}


def _build_progress(
    row: ScanRunRow, tool_runs: list[ToolRunRow]
) -> ScanProgressResponse:
    sp = ScansService.compute_progress(row, tool_runs)
    return ScanProgressResponse(
        id=row.id,
        status=row.status,
        progress=sp.progress,
        current_segment=None,
        segment_label=None,
        tool_runs_summary=ToolRunsSummary(
            queued=sp.counts.queued,
            running=sp.counts.running,
            done=sp.counts.done,
            failed=sp.counts.failed,
            skipped=sp.counts.skipped,
        ),
    )


# Project-scoped routes: literal segments first, then parameterized


@v1_router.get(
    "/{project_id}/scans/config",
    response_model=ScanConfigResponse,
)
async def get_scans_config(
    project_id: int,
    request: Request,
) -> ScanConfigResponse:
    """Return the inputs the SPA needs to compose a scan start
    request."""
    row = _resolve_project(request, project_id)

    base_path: str = request.app.state.base_path
    project_name: str = row.name
    tool_registry = request.app.state.tool_registry

    paths = ProjectPaths.from_registry_row(row)
    overrides_repo = create_overrides_repo(paths.findings_db)
    discover_tools(
        tool_registry,
        base_path,
        project_name=project_name,
        overrides_repo=overrides_repo,
    )

    repo_service = ProjectRepositoriesService.build(
        request.app.state.project_registry,
        request.app.state.base_path,
    )
    repos: list[ScanConfigRepo] = []
    for r in repo_service.list_active(project_id):
        assert isinstance(r.id, int)  # list_active filters to DB-resident repos
        service = r.services[0] if r.services else None
        if service is None:
            continue
        location = "docker" if service.container_name else "local"
        repos.append(
            ScanConfigRepo(
                id=r.id,
                name=r.name,
                source=",".join(service.type) or "unknown",
                location=location,
            )
        )

    tools: list[ScanConfigTool] = []
    for tw in tool_registry.get_all_tools():
        tools.append(
            ScanConfigTool(
                id=tw.name,
                name=tw.name.replace("_", " ").replace("-", " ").title(),
                domain=getattr(tw, "category", "") or "",
                enabled=True,
                requires_arg_profile=getattr(tw, "requires_arg_profile", False),
            )
        )

    return ScanConfigResponse(
        repos=repos,
        tools=tools,
        domains=list(SEGMENT_ORDER),
    )


@v1_router.get("/{project_id}/scans/events")
async def scans_events(
    project_id: int,
    request: Request,
    run_id: int | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream for scan lifecycle events, with snapshot on connect
    to sync client state immediately."""
    service = _service(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("scan")

    snapshot_event = await _build_snapshot(service, project_id, run_id)

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
                if run_id is not None and payload.get("run_id") != run_id:
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("scan", sub_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v1_router.post(
    "/{project_id}/scans/cancel-all",
    response_model=ScanCancelAllResponse,
)
async def cancel_all_scans(
    project_id: int,
    request: Request,
) -> ScanCancelAllResponse:
    """Cancel every active scan for this project."""
    service = _service(request, project_id)
    cancelled = await asyncio.to_thread(service.cancel_all)
    return ScanCancelAllResponse(cancelled=cancelled)


@v1_router.get(
    "/{project_id}/scans",
    response_model=ScansListResponse,
)
async def list_scans(
    project_id: int,
    request: Request,
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ScansListResponse:
    """Paginated scan history for a project, newest-first."""
    service = _service(request, project_id)
    try:
        service.validate_status(status)
    except ScanValidationError as exc:
        raise ApiValidationError(
            "Scan query validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc
    repo = service.run_repo
    rows, total = await asyncio.to_thread(
        repo.list_for_project,
        project_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return ScansListResponse(
        items=[scan_run_to_summary(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.post(
    "/{project_id}/scans",
    response_model=ScanRunSummary,
    status_code=202,
)
async def start_scan(
    project_id: int,
    request: Request,
    body: ScanStartRequest,
) -> ScanRunSummary:
    """Queue a new scan in a worker thread.

    Returns 409 ``JOB_ALREADY_RUNNING`` if another scan is in progress.
    """
    row = _resolve_project(request, project_id)
    project_name: str = row.name
    base_path: str = request.app.state.base_path
    tool_registry = request.app.state.tool_registry

    paths = ProjectPaths.from_registry_row(row)
    overrides_repo = create_overrides_repo(paths.findings_db)
    discover_tools(
        tool_registry,
        base_path,
        project_name=project_name,
        overrides_repo=overrides_repo,
    )

    repos_service = ProjectRepositoriesService.build(
        request.app.state.project_registry,
        request.app.state.base_path,
    )
    profiles_repo = create_arg_profiles_repo(paths.findings_db)
    service = _service(request, project_id)

    try:
        resolved = await asyncio.to_thread(
            service.validate_start_request,
            repo_ids=body.repoIds,
            tool_ids=body.toolIds,
            skip_tool_ids=body.skipToolIds,
            domains=body.domains,
            arg_profile_ids=body.argProfileIds,
            repos_service=repos_service,
            tool_registry=tool_registry,
            profiles_repo=profiles_repo,
        )
    except ScanValidationError as exc:
        raise ApiValidationError(
            "Scan validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc

    sink = EventBusScanSink(request.app.state.event_bus)
    run_repo, chat_session_repo, _, _ = create_scan_repos(paths.findings_db)
    finding_repo = create_finding_repo(paths.findings_db)
    repo_repo = create_repo_repo(paths.findings_db)
    url_finding_repo = create_url_finding_repo(paths.findings_db)

    try:
        handle = await asyncio.to_thread(
            get_scan_service().start_scan,
            project_id=project_id,
            project_name=project_name,
            base_path=base_path,
            tool_registry=tool_registry,
            run_repo=run_repo,
            chat_session_repo=chat_session_repo,
            finding_repo=finding_repo,
            repo_repo=repo_repo,
            url_finding_repo=url_finding_repo,
            profiles_repo=profiles_repo,
            repo_ids=tuple(resolved.repo_names),
            tool_ids=tuple(body.toolIds),
            domains=tuple(body.domains),
            skip_tool_ids=tuple(body.skipToolIds),
            skip_enrichment=body.skipEnrichment,
            arg_profile_ids=body.argProfileIds,
            since_commit=body.sinceCommit,
            git_diff=create_git_diff() if body.sinceCommit else None,
            prompt=NoApprovalPromptAdapter(),
            event_sink=sink,
        )
    except JobBusy as exc:
        raise JobBusyError("scan", exc.current_holder) from exc

    fresh = await asyncio.to_thread(service.run_repo.get, handle.run_id)
    if fresh is None:
        raise NotFound(f"scan run {handle.run_id} not found after creation")
    return scan_run_to_summary(fresh)


@v1_router.post(
    "/{project_id}/scans/{run_id}/cancel",
    response_model=ScanCancelResponse,
    status_code=202,
)
async def cancel_scan(
    project_id: int,
    run_id: int,
    request: Request,
) -> ScanCancelResponse:
    """Request cancellation of a specific scan run."""
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.cancel_scan, run_id)
    except ScanNotFound as exc:
        raise NotFound(f"scan run {run_id} not found") from exc
    except ScanNotCancellable as exc:
        raise Conflict(
            f"scan run {run_id} is not in a cancellable state",
            code="SCAN_NOT_CANCELLABLE",
            details={"status": exc.status},
        ) from exc
    return ScanCancelResponse(id=run_id, status="cancelling")


@v1_router.get(
    "/{project_id}/scans/{run_id}/progress",
    response_model=ScanProgressResponse,
)
async def scan_progress(
    project_id: int,
    run_id: int,
    request: Request,
) -> ScanProgressResponse:
    """Point-in-time progress snapshot for a single scan run."""
    service = _service(request, project_id)
    repo = service.run_repo
    bundle = await asyncio.to_thread(repo.get_with_tool_runs, run_id)
    if bundle is None:
        raise NotFound(f"scan run {run_id} not found")
    scan_row, tool_rows = bundle
    if scan_row.project_id != project_id:
        raise NotFound(f"scan run {run_id} not found")
    return _build_progress(scan_row, tool_rows)


@v1_router.get(
    "/{project_id}/scans/{run_id}",
    response_model=ScanDetailResponse,
)
async def get_scan(
    project_id: int,
    run_id: int,
    request: Request,
) -> ScanDetailResponse:
    """Full scan run with the per-tool execution records."""
    service = _service(request, project_id)
    repo = service.run_repo
    bundle = await asyncio.to_thread(repo.get_with_tool_runs, run_id)
    if bundle is None:
        raise NotFound(f"scan run {run_id} not found")
    scan_row, tool_rows = bundle
    if scan_row.project_id != project_id:
        raise NotFound(f"scan run {run_id} not found")
    return ScanDetailResponse(
        id=scan_row.id,
        project_id=scan_row.project_id,
        status=scan_row.status,
        started_at=scan_row.started_at,
        finished_at=scan_row.finished_at,
        repo_ids=scan_row.repo_ids,
        tool_ids=scan_row.tool_ids,
        domains=scan_row.domains,
        findings_count=scan_row.findings_count,
        skip_enrichment=scan_row.skip_enrichment,
        tool_runs=[_tool_run_to_item(r) for r in tool_rows],
    )


async def _build_snapshot(
    service: ScansService,
    project_id: int,
    run_id: int | None,
) -> BusEvent:
    """Build a 'snapshot' BusEvent for the SSE on-connect frame."""
    payload: dict[str, Any] = {
        "run_id": run_id,
        "project_id": project_id,
    }
    if run_id is not None:
        bundle = await asyncio.to_thread(service.run_repo.get_with_tool_runs, run_id)
        if bundle is not None:
            scan_row, tool_rows = bundle
            if scan_row.project_id == project_id:
                progress = _build_progress(scan_row, tool_rows)
                handle = service.peek_active_run(run_id)
                payload.update(
                    status=scan_row.status,
                    progress=progress.progress,
                    current_segment=None,
                    segment_label=None,
                    current_repo=handle.current_repo if handle else None,
                    current_tool=handle.current_tool if handle else None,
                    tool_runs=[_tool_run_to_item(r).model_dump() for r in tool_rows],
                    project_id=scan_row.project_id,
                    started_at=scan_row.started_at,
                )
    else:
        active_handles = service.list_active_runs()
        payload["active_run_ids"] = [h.run_id for h in active_handles]
        # Payload includes current (repo, tool) for each active run so
        # late subscribers can render the live label immediately.
        payload["active_runs"] = [
            {
                "run_id": h.run_id,
                "repo": h.current_repo,
                "tool": h.current_tool,
            }
            for h in active_handles
        ]

    return BusEvent(
        event_id=new_event_id(),
        job_id="scan",
        stream="scan",
        event_type="snapshot",
        payload=payload,
        ts=datetime.now(UTC),
    )

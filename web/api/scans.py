"""Scan endpoints (config, start, history, detail, cancel, SSE,
progress).

Endpoint surface (all project-scoped after Phase 6.8):

- ``GET    /api/v1/projects/{project_id}/scans/config``
- ``GET    /api/v1/projects/{project_id}/scans``               (history list)
- ``POST   /api/v1/projects/{project_id}/scans``               (start scan)
- ``GET    /api/v1/projects/{project_id}/scans/events``        (SSE)
- ``POST   /api/v1/projects/{project_id}/scans/cancel-all``
- ``GET    /api/v1/projects/{project_id}/scans/{run_id}``      (detail)
- ``GET    /api/v1/projects/{project_id}/scans/{run_id}/progress``
- ``POST   /api/v1/projects/{project_id}/scans/{run_id}/cancel``

Route ordering (Phase 4 lesson): literal-segment routes are decorated
**before** parameterized routes so Starlette doesn't shadow them.
"""

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
from application.tools.registry import discover_tools, tool_registry
from application.tools.scan_run_registry import get_scan_run_registry
from application.tools.scan_service import get_scan_service
from core.project_paths import ProjectPaths
from domain.scans.entry import ScanRunRow, ToolRunRow
from domain.tools.scan_types import SEGMENT_ORDER
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import SCAN_RUN_STATUSES, RunRepository
from web.adapters.event_bus_scan_sink import EventBusScanSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
from web.api._errors import Conflict, JobBusyError, NotFound, ValidationError
from web.api._project_resolver import _resolve_project
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

logger = logging.getLogger("tally.web.scans")


# All routes are project-scoped under /api/v1/projects/...
v1_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_repo(row: dict) -> RunRepository:
    paths = ProjectPaths.from_registry_row(row)
    return RunRepository(ConnectionFactory(paths.findings_db))


def _scan_run_to_summary(row: ScanRunRow) -> ScanRunSummary:
    return ScanRunSummary(
        id=row.id,
        project_id=row.project_id,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        repo_ids=row.repo_ids,
        tool_ids=row.tool_ids,
        domains=row.domains,
        findings_count=row.findings_count,
        skip_enrichment=row.skip_enrichment,
    )


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


def _validate_status(status: str | None) -> None:
    if status is None:
        return
    if status not in SCAN_RUN_STATUSES:
        raise ValidationError(
            f"unknown scan status {status!r}",
            details={"allowed": list(SCAN_RUN_STATUSES)},
        )


def _build_progress(
    row: ScanRunRow, tool_runs: list[ToolRunRow]
) -> ScanProgressResponse:
    counts = {"queued": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0}
    for tr in tool_runs:
        if tr.skip_reason:
            counts["skipped"] += 1
            continue
        st = (tr.status or "queued").lower()
        if st in counts:
            counts[st] += 1
        else:
            counts["queued"] += 1
    total = len(tool_runs)
    finished = counts["done"] + counts["failed"] + counts["skipped"]
    progress = int(round(finished * 100 / total)) if total > 0 else 0
    if row.status in {"done", "failed", "cancelled"}:
        progress = 100
    return ScanProgressResponse(
        id=row.id,
        status=row.status,
        progress=progress,
        current_segment=None,
        segment_label=None,
        tool_runs_summary=ToolRunsSummary(**counts),
    )


# ---------------------------------------------------------------------------
# Project-scoped routes: literal segments first, then parameterized
# ---------------------------------------------------------------------------


@v1_router.get(
    "/{project_id}/scans/config",
    response_model=ScanConfigResponse,
)
async def get_scans_config(
    project_id: int,
    request: Request,
) -> ScanConfigResponse:
    """Return the inputs the SPA needs to compose a scan-start request."""
    row = _resolve_project(request, project_id)

    base_path: str = request.app.state.base_path
    project_name: str = row["name"]

    # Tool registry is process-shared; rediscover with this project's overrides
    # before reading so domain mappings reflect the project's commands.json.
    discover_tools(base_path, project_name=project_name)

    repo_service = ProjectRepositoriesService.from_request(request)
    repos: list[ScanConfigRepo] = []
    for r in repo_service.list_active(project_id):
        assert isinstance(r.id, int)  # list_active filters to DB-resident repos
        data = r.model_dump()
        location = "docker" if data.get("container_name") else "local"
        repos.append(
            ScanConfigRepo(
                id=r.id,
                name=r.name,
                source=",".join(data.get("type", [])) or "unknown",
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
    """SSE stream emitting scan lifecycle events for this project.

    Filters live events by ``project_id`` (always, from the path) and
    optionally ``run_id``. On connect emits a ``snapshot`` event built
    from the current ``scan_runs`` row(s) so the SPA can sync without
    waiting for the next live tick.
    """
    row = _resolve_project(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("scan")

    snapshot_event = await _build_snapshot(row, project_id, run_id)

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
    row = _resolve_project(request, project_id)
    registry = get_scan_run_registry()
    cancelled: list[int] = []
    for handle in registry.list_for_project(project_id):
        handle.cancel_token.set()
        cancelled.append(handle.run_id)

    if cancelled:
        repo = _make_run_repo(row)
        for run_id in cancelled:
            try:
                await asyncio.to_thread(repo.set_status, run_id, "cancelling")
            except Exception:  # noqa: BLE001
                logger.exception("failed to mark scan %d cancelling", run_id)

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
    row = _resolve_project(request, project_id)
    _validate_status(status)
    repo = _make_run_repo(row)
    rows, total = await asyncio.to_thread(
        repo.list_for_project,
        project_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return ScansListResponse(
        items=[_scan_run_to_summary(r) for r in rows],
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
    project_name: str = row["name"]
    base_path: str = request.app.state.base_path

    discover_tools(base_path, project_name=project_name)
    repo_lookup = ProjectRepositoriesService.from_request(request).find_by_ids(
        project_id, body.repoIds
    )
    if repo_lookup.missing:
        raise ValidationError(
            f"unknown repo ids: {repo_lookup.missing}",
            details={
                "unknown": repo_lookup.missing,
                "available": repo_lookup.available,
            },
        )
    _validate_tool_ids(body.toolIds + body.skipToolIds)
    _validate_domains(body.domains)

    repo_names = [repo_lookup.found[rid].name for rid in body.repoIds]

    paths = ProjectPaths.from_registry_row(row)
    sink = EventBusScanSink(request.app.state.event_bus)

    try:
        handle = await asyncio.to_thread(
            get_scan_service().start_scan,
            project_id=project_id,
            project_name=project_name,
            base_path=base_path,
            paths=paths,
            repo_ids=tuple(repo_names),
            tool_ids=tuple(body.toolIds),
            domains=tuple(body.domains),
            skip_tool_ids=tuple(body.skipToolIds),
            skip_enrichment=body.skipEnrichment,
            prompt=NoApprovalPromptAdapter(),
            event_sink=sink,
        )
    except JobBusy as exc:
        raise JobBusyError("scan", exc.current_holder) from exc

    repo = _make_run_repo(row)
    fresh = await asyncio.to_thread(repo.get, handle.run_id)
    if fresh is None:
        raise NotFound(f"scan run {handle.run_id} not found after creation")
    return _scan_run_to_summary(fresh)


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
    row = _resolve_project(request, project_id)
    repo = _make_run_repo(row)

    handle = get_scan_run_registry().get(run_id)
    if handle is None:
        scan_row = await asyncio.to_thread(repo.get, run_id)
        if scan_row is None or scan_row.project_id != project_id:
            raise NotFound(f"scan run {run_id} not found")
        raise Conflict(
            f"scan run {run_id} is not in a cancellable state",
            code="SCAN_NOT_CANCELLABLE",
            details={"status": scan_row.status or "unknown"},
        )

    if handle.project_id != project_id:
        raise NotFound(f"scan run {run_id} not found")

    handle.cancel_token.set()
    try:
        await asyncio.to_thread(repo.set_status, run_id, "cancelling")
    except Exception:  # noqa: BLE001
        logger.exception("failed to mark scan %d cancelling", run_id)

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
    row = _resolve_project(request, project_id)
    repo = _make_run_repo(row)
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
    row = _resolve_project(request, project_id)
    repo = _make_run_repo(row)
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


# ---------------------------------------------------------------------------
# More helpers (after route declarations to keep the public surface visible)
# ---------------------------------------------------------------------------


def _validate_tool_ids(tool_ids: list[str]) -> None:
    if not tool_ids:
        return
    valid = {tw.name for tw in tool_registry.get_all_tools()}
    missing = [t for t in tool_ids if t not in valid]
    if missing:
        raise ValidationError(
            f"unknown tool names: {missing}",
            details={"unknown": missing, "available": sorted(valid)},
        )


def _validate_domains(domains: list[str]) -> None:
    if not domains:
        return
    valid = set(SEGMENT_ORDER)
    missing = [d for d in domains if d not in valid]
    if missing:
        raise ValidationError(
            f"unknown domains: {missing}",
            details={"unknown": missing, "available": sorted(valid)},
        )


async def _build_snapshot(
    row: dict,
    project_id: int,
    run_id: int | None,
) -> BusEvent:
    """Build a 'snapshot' BusEvent for the SSE on-connect frame."""
    payload: dict[str, Any] = {
        "run_id": run_id,
        "project_id": project_id,
    }
    registry = get_scan_run_registry()
    if run_id is not None:
        repo = _make_run_repo(row)
        bundle = await asyncio.to_thread(repo.get_with_tool_runs, run_id)
        if bundle is not None:
            scan_row, tool_rows = bundle
            if scan_row.project_id == project_id:
                progress = _build_progress(scan_row, tool_rows)
                handle = registry.get(run_id)
                payload.update(
                    status=scan_row.status,
                    progress=progress.progress,
                    current_segment=None,
                    segment_label=None,
                    current_repo=handle.current_repo if handle else None,
                    current_tool=handle.current_tool if handle else None,
                    tool_runs=[_tool_run_to_item(r).model_dump() for r in tool_rows],
                    project_id=scan_row.project_id,
                )
    else:
        active_handles = registry.list_for_project(project_id)
        payload["active_run_ids"] = [h.run_id for h in active_handles]
        # Sibling field carrying the most recent (repo, tool) per active
        # run so a mid-scan SSE subscriber can render the live label
        # immediately instead of waiting for the next tool_started event.
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

"""Triage endpoints (history, detail, dispatch, cancel, SSE).

Endpoints:
- GET  /api/v1/projects/{project_id}/triage (history)
- GET  /api/v1/projects/{project_id}/triage/events (SSE)
- POST /api/v1/projects/{project_id}/triage (start)
- POST /api/v1/projects/{project_id}/triage/{scan_run_id}/cancel
- GET  /api/v1/projects/{project_id}/triage/{scan_run_id} (detail)

A triage run is identified by scan_run_id. The runner picks the latest
scan_runs row for the project and writes triage_batches keyed by that id.
Route ordering: literal-segment routes registered before parameterized.
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
from application.triage.run_registry import get_triage_run_registry
from application.triage.runner import NoScanRunError
from application.triage.triage_service import (
    TriageNotResumableError,
    TriageService,
)
from domain.triage.entry import TriageBatchRow
from domain.triage.entry import TriageRunSummary as TriageRunSummaryRow
from factories.persistence import ProjectNotFound, create_triage_service
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from web.adapters.event_bus_triage_sink import EventBusTriageSink
from web.api._errors import Conflict, JobBusyError, NotFound, ValidationError
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    TriageBatchItem,
    TriageCancelResponse,
    TriageDetailResponse,
    TriageRunSummary,
    TriagesListResponse,
    TriageStartRequest,
)

logger = logging.getLogger("tally.web.triage")


# Single router mounted at /api/v1/projects.
v1_router = APIRouter()


# Helpers


def _service(request: Request, project_id: int) -> TriageService:
    """Build a TriageService for *project_id* or raise 404."""
    try:
        return create_triage_service(request.app.state.project_registry, project_id)
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _segment_for(batch: TriageBatchRow) -> str | None:
    """Best-effort segment lookup from the persisted batch_data."""
    if not batch.batch_data:
        return None
    first = batch.batch_data[0]
    if isinstance(first, dict):
        return first.get("segment")
    return None


def _summary_to_response(
    summary: TriageRunSummaryRow,
    project_id: int,
) -> TriageRunSummary:
    return TriageRunSummary(
        scan_run_id=summary.scan_run_id,
        project_id=project_id,
        status=summary.status,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        total_findings=summary.total_findings,
        processed_findings=summary.processed_findings,
    )


def _batch_to_item(batch: TriageBatchRow) -> TriageBatchItem:
    return TriageBatchItem(
        id=batch.id,
        scan_run_id=batch.run_id,
        segment=_segment_for(batch),
        finding_ids=batch.finding_ids,
        status=batch.status,
        attempts=batch.run_attempts,
        started_at=batch.started_at,
        finished_at=batch.completed_at,
        response_preview=None,
        error=None,
    )


# /api/v1/projects/{project_id}/triage: history (literal-segment first)


@v1_router.get(
    "/{project_id}/triage",
    response_model=TriagesListResponse,
)
async def list_triage_runs(
    project_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> TriagesListResponse:
    """Paginated triage history: scan_run_ids that have triage_batches."""
    service = _service(request, project_id)
    triage_repo = service.triage_repo
    run_ids, total = await asyncio.to_thread(
        triage_repo.list_run_ids_for_project,
        offset=offset,
        limit=limit,
    )
    items: list[TriageRunSummary] = []
    for run_id in run_ids:
        summary = await asyncio.to_thread(triage_repo.summarize_for_run, run_id)
        if summary is None:
            continue
        items.append(_summary_to_response(summary, project_id))
    return TriagesListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.get(
    "/{project_id}/triage/active",
    response_model=TriageRunSummary | None,
)
async def get_active_triage(
    project_id: int,
    request: Request,
) -> TriageRunSummary | None:
    """Return the currently-running triage for *project_id*, or ``null``.

    Liveness is sourced from :class:`TriageRunRegistry` (process-singleton
    of in-flight worker handles). The persisted summary is refreshed via
    ``summarize_for_run``; when the worker has registered but no batches
    have been written yet, a synthetic ``queued`` placeholder is returned.
    """
    service = _service(request, project_id)
    handles = get_triage_run_registry().list_for_project(project_id)
    if not handles:
        return None
    if len(handles) > 1:
        logger.warning(
            "more than one triage handle for project %d; returning newest",
            project_id,
        )
    handle = handles[-1]
    triage_repo = service.triage_repo
    summary = await asyncio.to_thread(triage_repo.summarize_for_run, handle.scan_run_id)
    if summary is None:
        return TriageRunSummary(
            scan_run_id=handle.scan_run_id,
            project_id=project_id,
            status="queued",
            started_at=None,
            finished_at=None,
            total_findings=0,
            processed_findings=0,
        )
    return _summary_to_response(summary, project_id)


@v1_router.get(
    "/{project_id}/triage/latest",
    response_model=TriageRunSummary,
)
async def get_latest_triage(
    project_id: int,
    request: Request,
) -> TriageRunSummary:
    """Return the most recent triage run summary for *project_id*.

    404 when the project has zero triage history.
    """
    service = _service(request, project_id)
    triage_repo = service.triage_repo
    run_ids, _total = await asyncio.to_thread(
        triage_repo.list_run_ids_for_project,
        offset=0,
        limit=1,
    )
    if not run_ids:
        raise NotFound(
            f"project {project_id} has no triage history",
        )
    summary = await asyncio.to_thread(triage_repo.summarize_for_run, run_ids[0])
    if summary is None:  # pragma: no cover - defensive
        raise NotFound(
            f"project {project_id} has no triage history",
        )
    return _summary_to_response(summary, project_id)


@v1_router.get("/{project_id}/triage/events")
async def triage_events(
    project_id: int,
    request: Request,
    scan_run_id: int | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream emitting triage lifecycle events for *project_id*.

    Optional ``scan_run_id`` query param filters to a single triage.
    On connect emits a ``snapshot`` event built from the current
    triage state so the SPA can sync without waiting for the next live
    tick.
    """
    service = _service(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("triage")

    snapshot_event = await _build_snapshot(service, project_id, scan_run_id)

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
                if (
                    scan_run_id is not None
                    and payload.get("scan_run_id") != scan_run_id
                ):
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("triage", sub_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v1_router.post(
    "/{project_id}/triage",
    response_model=TriageRunSummary,
    status_code=202,
)
async def start_triage(
    project_id: int,
    request: Request,
    body: TriageStartRequest,
) -> TriageRunSummary:
    """Queue a new triage in a worker thread.

    The application core picks the latest scan_run_id for the project.
    Returns 409 ``JOB_ALREADY_RUNNING`` if another triage is in
    progress, 422 if ``acknowledge_injection_risk`` is missing/false,
    or 404 if the project has no scan runs to triage.
    """
    if not body.acknowledge_injection_risk:
        raise ValidationError(
            "acknowledge_injection_risk must be true to dispatch triage",
            details={"field": "acknowledge_injection_risk"},
        )

    row = _resolve_project(request, project_id)
    project_name: str = row.name
    base_path: str = request.app.state.base_path

    service = _service(request, project_id)
    sink = EventBusTriageSink(request.app.state.event_bus)
    finding_ids = tuple(body.finding_ids) if body.finding_ids else None
    try:
        handle = await asyncio.to_thread(
            service.start_triage,
            base_path=base_path,
            project_id=project_id,
            project_name=project_name,
            tool_registry=request.app.state.tool_registry,
            event_sink=sink,
            finding_ids=finding_ids,
        )
    except NoScanRunError as exc:
        raise NotFound(
            f"project {project_name!r} has no scan runs; run a scan before triage",
        ) from exc
    except JobBusy as exc:
        raise JobBusyError("triage", exc.current_holder) from exc

    summary = await asyncio.to_thread(
        service.triage_repo.summarize_for_run, handle.scan_run_id
    )
    if summary is None:
        # No batches yet; return a queued placeholder.
        return TriageRunSummary(
            scan_run_id=handle.scan_run_id,
            project_id=project_id,
            status="queued",
            started_at=None,
            finished_at=None,
            total_findings=0,
            processed_findings=0,
        )
    return _summary_to_response(summary, project_id)


# Parameterized: /{project_id}/triage/{scan_run_id}/...


@v1_router.post(
    "/{project_id}/triage/{scan_run_id}/cancel",
    response_model=TriageCancelResponse,
    status_code=202,
)
async def cancel_triage(
    project_id: int,
    scan_run_id: int,
    request: Request,
) -> TriageCancelResponse:
    """Request cancellation of an in-progress triage."""
    service = _service(request, project_id)
    handle = get_triage_run_registry().get(scan_run_id)
    if handle is None:
        # Distinguish "never existed" from "already finished" by
        # checking persisted state.
        summary = await asyncio.to_thread(
            service.triage_repo.summarize_for_run, scan_run_id
        )
        if summary is None:
            raise NotFound(
                f"no triage runs found for scan_run_id {scan_run_id}",
            )
        raise Conflict(
            f"triage scan_run_id {scan_run_id} is not in a cancellable state",
            code="TRIAGE_NOT_CANCELLABLE",
            details={"status": summary.status},
        )

    if handle.project_id != project_id:
        raise NotFound(
            f"no triage runs found for scan_run_id {scan_run_id}",
        )

    handle.cancel_token.set()
    return TriageCancelResponse(scan_run_id=scan_run_id, status="cancelling")


@v1_router.post(
    "/{project_id}/triage/{scan_run_id}/resume",
    response_model=TriageRunSummary,
    status_code=202,
)
async def resume_triage(
    project_id: int,
    scan_run_id: int,
    request: Request,
    body: TriageStartRequest,
) -> TriageRunSummary:
    """Resume a previously failed or stranded triage run.

    Resumability rule: status must be ``'failed'`` or ``'running'``
    (``'running'`` here means a worker crashed leaving stranded
    pending/in_progress batches). Terminal states (``'done'`` and
    ``'cancelled'``) return 409 ``TRIAGE_NOT_RESUMABLE``.

    The active-worker case (another live triage holding the lock)
    returns 409 ``JOB_ALREADY_RUNNING``.
    """
    if not body.acknowledge_injection_risk:
        raise ValidationError(
            "acknowledge_injection_risk must be true to resume triage",
            details={"field": "acknowledge_injection_risk"},
        )

    row = _resolve_project(request, project_id)
    project_name: str = row.name
    base_path: str = request.app.state.base_path

    service = _service(request, project_id)
    sink = EventBusTriageSink(request.app.state.event_bus)
    try:
        await asyncio.to_thread(
            service.resume_triage,
            base_path=base_path,
            project_id=project_id,
            project_name=project_name,
            scan_run_id=scan_run_id,
            tool_registry=request.app.state.tool_registry,
            event_sink=sink,
        )
    except TriageNotResumableError as exc:
        if exc.status is None:
            raise NotFound(
                f"no triage runs found for scan_run_id {scan_run_id}",
            ) from exc
        raise Conflict(
            f"triage scan_run_id {scan_run_id} is not resumable "
            f"(status={exc.status!r})",
            code="TRIAGE_NOT_RESUMABLE",
            details={"status": exc.status},
        ) from exc
    except JobBusy as exc:
        raise JobBusyError("triage", exc.current_holder) from exc

    refreshed = await asyncio.to_thread(
        service.triage_repo.summarize_for_run, scan_run_id
    )
    if refreshed is None:  # pragma: no cover - defensive (we already checked)
        return TriageRunSummary(
            scan_run_id=scan_run_id,
            project_id=project_id,
            status="queued",
            started_at=None,
            finished_at=None,
            total_findings=0,
            processed_findings=0,
        )
    return _summary_to_response(refreshed, project_id)


@v1_router.get(
    "/{project_id}/triage/{scan_run_id}",
    response_model=TriageDetailResponse,
)
async def get_triage(
    project_id: int,
    scan_run_id: int,
    request: Request,
) -> TriageDetailResponse:
    """Full triage detail with batches."""
    service = _service(request, project_id)
    triage_repo = service.triage_repo
    summary = await asyncio.to_thread(triage_repo.summarize_for_run, scan_run_id)
    if summary is None:
        raise NotFound(
            f"no triage runs found for scan_run_id {scan_run_id}",
        )
    batches = await asyncio.to_thread(triage_repo.list_for_run, scan_run_id)
    return TriageDetailResponse(
        scan_run_id=scan_run_id,
        project_id=project_id,
        status=summary.status,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        total_findings=summary.total_findings,
        processed_findings=summary.processed_findings,
        batches=[_batch_to_item(b) for b in batches],
    )


# Snapshot helper


async def _build_snapshot(
    service: TriageService,
    project_id: int,
    scan_run_id: int | None,
) -> BusEvent:
    """Build the on-connect ``snapshot`` BusEvent for a triage SSE stream."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "scan_run_id": scan_run_id,
    }
    if scan_run_id is not None:
        triage_repo = service.triage_repo
        summary = await asyncio.to_thread(triage_repo.summarize_for_run, scan_run_id)
        if summary is not None:
            batches = await asyncio.to_thread(triage_repo.list_for_run, scan_run_id)
            payload.update(
                status=summary.status,
                total_findings=summary.total_findings,
                processed_findings=summary.processed_findings,
                started_at=summary.started_at,
                finished_at=summary.finished_at,
                batches=[_batch_to_item(b).model_dump() for b in batches],
            )
    else:
        active = get_triage_run_registry().list_for_project(project_id)
        payload["active_scan_run_ids"] = [h.scan_run_id for h in active]

    return BusEvent(
        event_id=new_event_id(),
        job_id="triage",
        stream="triage",
        event_type="snapshot",
        payload=payload,
        ts=datetime.now(UTC),
    )

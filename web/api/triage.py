"""Phase 6 — Triage endpoints (history, detail, dispatch, cancel, SSE).

Endpoint surface per ``docs/roadmap/ui-planning/API/endpoints.md §6``:

- ``GET    /api/v1/projects/{project_id}/triage``                     (history)
- ``GET    /api/v1/projects/{project_id}/triage/events``              (SSE)
- ``POST   /api/v1/projects/{project_id}/triage``                     (start)
- ``POST   /api/v1/projects/{project_id}/triage/{scan_run_id}/cancel``
- ``GET    /api/v1/projects/{project_id}/triage/{scan_run_id}``       (detail)

A "triage run" is identified by ``scan_run_id`` — there is no separate
triage_id. The runner picks the latest ``scan_runs`` row for the
project and writes ``triage_batches`` keyed by that id. The SPA never
chooses the scan_run; the application core does.

Route ordering: literal-segment routes (``.../events``) registered
before parameterised routes (``.../{scan_run_id}``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.locking import JobBusy, get_registry
from core.project_paths import ProjectPaths
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import EOS, BusEvent
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import (
    TriageBatchRepository,
    TriageBatchRow,
)
from infrastructure.store.repositories.triage import (
    TriageRunSummary as TriageRunSummaryRow,
)
from web.adapters.triage_run_registry import get_triage_run_registry
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
from web.triage.runner import TriageRequest, start_triage_thread

logger = logging.getLogger("tally.web.triage")


# Single router mounted at /api/v1/projects.
v1_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repos(row: dict) -> tuple[RunRepository, TriageBatchRepository]:
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    return RunRepository(factory), TriageBatchRepository(factory)


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


# ---------------------------------------------------------------------------
# /api/v1/projects/{project_id}/triage — history (literal-segment first)
# ---------------------------------------------------------------------------


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
    row = _resolve_project(request, project_id)
    _, triage_repo = _make_repos(row)
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
    _resolve_project(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("triage")

    snapshot_event = await _build_snapshot(request, project_id, scan_run_id)

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
    project_name: str = row["name"]
    base_path: str = request.app.state.base_path

    run_repo, triage_repo = _make_repos(row)
    scan_run_id = await asyncio.to_thread(run_repo.latest_run_id)
    if scan_run_id is None:
        raise NotFound(
            f"project {project_name!r} has no scan runs; run a scan before triage",
        )

    lock_registry = get_registry()
    holder = f"triage-web:{new_event_id()[:8]}"
    try:
        lock_registry.acquire_job("triage", holder)
    except JobBusy as exc:
        raise JobBusyError("triage", exc.current_holder) from exc

    bus = request.app.state.event_bus
    triage_request = TriageRequest(
        finding_ids=tuple(body.finding_ids) if body.finding_ids else None,
    )

    try:
        start_triage_thread(
            base_path=base_path,
            project_name=project_name,
            project_id=project_id,
            scan_run_id=scan_run_id,
            request=triage_request,
            holder_token=holder,
            bus=bus,
            triage_run_registry=get_triage_run_registry(),
            lock_registry=lock_registry,
        )
    except Exception:
        try:
            lock_registry.release_job("triage", holder)
        except Exception:  # noqa: BLE001
            pass
        raise

    summary = await asyncio.to_thread(triage_repo.summarize_for_run, scan_run_id)
    if summary is None:
        # No batches yet — return a queued placeholder.
        return TriageRunSummary(
            scan_run_id=scan_run_id,
            project_id=project_id,
            status="queued",
            started_at=None,
            finished_at=None,
            total_findings=0,
            processed_findings=0,
        )
    return _summary_to_response(summary, project_id)


# ---------------------------------------------------------------------------
# Parameterised: /{project_id}/triage/{scan_run_id}/...
# ---------------------------------------------------------------------------


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
    _resolve_project(request, project_id)
    handle = get_triage_run_registry().get(scan_run_id)
    if handle is None:
        # Distinguish "never existed" from "already finished" by
        # checking persisted state.
        row = _resolve_project(request, project_id)
        _, triage_repo = _make_repos(row)
        summary = await asyncio.to_thread(triage_repo.summarize_for_run, scan_run_id)
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
    row = _resolve_project(request, project_id)
    _, triage_repo = _make_repos(row)
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


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------


async def _build_snapshot(
    request: Request,
    project_id: int,
    scan_run_id: int | None,
) -> BusEvent:
    """Build the on-connect ``snapshot`` BusEvent for a triage SSE stream."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "scan_run_id": scan_run_id,
    }
    if scan_run_id is not None:
        row = _resolve_project(request, project_id)
        _, triage_repo = _make_repos(row)
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

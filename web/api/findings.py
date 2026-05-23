"""Project-scoped findings endpoints (GET, PATCH, SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.events.types import EOS
from application.findings.findings_service import FindingsService
from application.locking import FindingsBusy
from domain.findings.severity import Severity
from domain.findings.sort import FindingSortColumn, SortDirection
from factories.persistence import (
    ProjectNotFound,
    create_findings_service,
)
from web.adapters.event_bus_finding_sink import EventBusFindingSink
from web.api._errors import FindingsLocked, Forbidden, NotFound
from web.api._finding_serialiser import serialise_finding as _serialise_finding
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    BatchFindingPatchRequest,
    BatchPatchResponse,
    FindingHistoryItem,
    FindingHistoryResponse,
    FindingPatchRequest,
    FindingResponse,
    FindingsCountsResponse,
    FindingsFacetsResponse,
    FindingsFilterOptionsResponse,
    FindingsListResponse,
    ManualFindingCreateRequest,
)
from web.sse import format_sse_frame

__all__ = ["router", "v1_router", "_serialise_finding"]

logger = logging.getLogger("tally.web.findings")

# Routes moved to v1_router; kept for backward-compat imports.
router = APIRouter()


def _service(request: Request, project_id: int) -> FindingsService:
    """Build a FindingsService for *project_id* or raise 404."""
    try:
        return create_findings_service(
            request.app.state.project_registry,
            project_id,
            knowledge_base_cache=request.app.state.knowledge_base_cache,
            base_path=request.app.state.base_path,
            event_sink=EventBusFindingSink(request.app.state.event_bus),
        )
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _translate_patch_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Reshape a Pydantic patch body into repository column schema."""
    fields: dict[str, Any] = {}
    for k, v in raw.items():
        if k.startswith("meta_"):
            fields[k.removeprefix("meta_")] = v
        elif k in ("finding_type", "cwe"):
            fields[k] = json.dumps(v)
        elif k == "should_report":
            fields["should_report"] = 1 if v else 0
        else:
            fields[k] = v
    return fields


v1_router = APIRouter()


@v1_router.get(
    "/{project_id}/findings/counts",
    response_model=FindingsCountsResponse,
)
async def get_findings_counts(
    project_id: int,
    request: Request,
) -> FindingsCountsResponse:
    """Return aggregate finding counts bucketed by five dimensions."""
    service = _service(request, project_id)
    data = await asyncio.to_thread(service.analyst.count_aggregates)
    return FindingsCountsResponse(**data)


@v1_router.get(
    "/{project_id}/findings/facets",
    response_model=FindingsFacetsResponse,
)
async def get_findings_facets(
    project_id: int,
    request: Request,
) -> FindingsFacetsResponse:
    """Return distinct filter values present in this project's findings."""
    service = _service(request, project_id)
    data = await asyncio.to_thread(service.analyst.distinct_facet_values)
    return FindingsFacetsResponse(**data)


@v1_router.get(
    "/{project_id}/findings/filter-options",
    response_model=FindingsFilterOptionsResponse,
)
async def get_findings_filter_options(
    project_id: int,
    request: Request,
    severity: list[str] | None = Query(default=None),
    confidence: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    domain: list[str] | None = Query(default=None),
    tool: list[str] | None = Query(default=None),
    repo_id: list[int] | None = Query(default=None),
    segment: list[str] | None = Query(default=None),
    finding_type: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
) -> FindingsFilterOptionsResponse:
    """Return filter option counts for each dimension under active filters.

    Counts reflect strict filter semantics (all active filters apply).
    Options with zero count are omitted to avoid clutter in the UI.
    """
    service = _service(request, project_id)

    if severity:
        for s in severity:
            Severity.from_label(s)

    conditions: list[tuple[str, str, list[Any]]] = []
    for col, values in [
        ("severity", severity),
        ("confidence", confidence),
        ("status", status),
        ("domain", domain),
        ("tool", tool),
        ("segment", segment),
        ("finding_type", finding_type),
    ]:
        if values:
            conditions.append((col, "=", list(values)))
    if repo_id:
        conditions.append(("repo_id", "=", [int(v) for v in repo_id]))

    filters: dict = {
        "conditions": conditions,
        "search": search,
    }

    data = await asyncio.to_thread(service.analyst.filter_options, filters)
    return FindingsFilterOptionsResponse(**data)


@v1_router.post(
    "/{project_id}/findings",
    response_model=FindingResponse,
    status_code=201,
)
async def create_manual_finding(
    project_id: int,
    request: Request,
    body: ManualFindingCreateRequest,
) -> dict:
    """Create a manually-reported finding."""
    service = _service(request, project_id)
    fields = body.model_dump(exclude_none=True)
    finding = await asyncio.to_thread(service.create_manual_finding, fields)
    repo_names = service.repo_name_lookup()
    serial = _serialise_finding(finding, service.lock_state_for(finding.id))
    rid = serial.get("repo_id")
    if isinstance(rid, int):
        serial["repo_name"] = repo_names.get(rid, "")
    else:
        serial["repo_name"] = ""
    return serial


@v1_router.get(
    "/{project_id}/findings",
    response_model=FindingsListResponse,
)
async def list_findings(
    project_id: int,
    request: Request,
    severity: list[str] | None = Query(default=None),
    confidence: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    domain: list[str] | None = Query(default=None),
    tool: list[str] | None = Query(default=None),
    repo_id: list[int] | None = Query(default=None),
    segment: list[str] | None = Query(default=None),
    finding_type: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None, pattern="^(asc|desc)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> FindingsListResponse:
    """Return a paginated, filtered, sorted list of findings.

    ``repo_id`` (integer DB id) is the canonical repo filter. Each
    response item carries both ``repo_id`` and ``repo_name`` so callers
    do not have to JOIN client-side.
    """
    service = _service(request, project_id)

    # ValueError from invalid severity labels surfaces as 422 via the
    # global error handler.
    if severity:
        for s in severity:
            Severity.from_label(s)

    sort_col: FindingSortColumn | None = None
    if sort:
        sort_col = FindingSortColumn.from_label(sort)
    sort_dir: SortDirection | None = None
    if order:
        sort_dir = SortDirection.from_label(order)

    conditions: list[tuple[str, str, list[Any]]] = []
    for col, values in [
        ("severity", severity),
        ("confidence", confidence),
        ("status", status),
        ("domain", domain),
        ("tool", tool),
        ("segment", segment),
        ("finding_type", finding_type),
    ]:
        if values:
            conditions.append((col, "=", list(values)))
    if repo_id:
        conditions.append(("repo_id", "=", [int(v) for v in repo_id]))

    filters: dict = {
        "conditions": conditions,
        "sort_by": sort_col,
        "sort_dir": sort_dir,
        "offset": offset,
        "limit": limit,
        "search": search,
    }

    total = await asyncio.to_thread(service.analyst.search_count, filters)
    rows = await asyncio.to_thread(service.analyst.search_raw, filters)

    repo_name_by_id = service.repo_name_lookup()
    items: list[FindingResponse] = []
    for r in rows:
        serial = _serialise_finding(r, service.lock_state_for(r.id))
        rid = serial.get("repo_id")
        if isinstance(rid, int):
            serial["repo_name"] = repo_name_by_id.get(rid, "")
        else:
            serial["repo_name"] = ""
        items.append(FindingResponse.model_validate(serial))
    return FindingsListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.get("/{project_id}/findings/events")
async def findings_events(
    project_id: int,
    request: Request,
) -> StreamingResponse:
    """Stream finding_updated events for this project via SSE.

    Sends only new events (no snapshot on connect). Each event carries
    the full serialized finding record and project_id for routing.
    """
    _resolve_project(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("finding")

    async def event_stream() -> AsyncIterator[str]:
        try:
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
                if item.payload.get("project_id") != project_id:
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("finding", sub_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v1_router.get(
    "/{project_id}/findings/{finding_id}",
    response_model=FindingResponse,
)
async def get_finding(
    project_id: int,
    finding_id: int,
    request: Request,
) -> dict:
    """Return a single finding by integer primary key."""
    service = _service(request, project_id)
    finding = await asyncio.to_thread(service.analyst.get_finding, finding_id)
    if finding is None:
        raise NotFound("Finding not found")
    return _serialise_finding(finding, service.lock_state_for(finding.id))


@v1_router.delete(
    "/{project_id}/findings/{finding_id}",
    status_code=204,
)
async def delete_finding(
    project_id: int,
    finding_id: int,
    request: Request,
) -> None:
    """Delete a manual finding."""
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.delete_manual_finding, finding_id)
    except LookupError as exc:
        raise NotFound(str(exc)) from exc
    except PermissionError as exc:
        raise Forbidden(str(exc)) from exc
    except FindingsBusy as exc:
        raise FindingsLocked(exc.conflicting_ids, exc.holders) from exc


@v1_router.get(
    "/{project_id}/findings/{finding_id}/history",
    response_model=FindingHistoryResponse,
)
async def get_finding_history(
    project_id: int,
    finding_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> FindingHistoryResponse:
    """Return paginated mutation history for a single finding."""
    service = _service(request, project_id)
    finding = await asyncio.to_thread(service.analyst.get_finding, finding_id)
    if finding is None:
        raise NotFound("Finding not found")
    history_repo = service.history_repo
    total = await asyncio.to_thread(history_repo.count_for_finding, finding_id)
    items = await asyncio.to_thread(
        history_repo.list_for_finding, finding_id, offset=offset, limit=limit
    )
    return FindingHistoryResponse(
        items=[
            FindingHistoryItem(
                id=h.id,
                finding_id=h.finding_id,
                timestamp=h.timestamp,
                before_values=h.before_values,
                after_values=h.after_values,
                inference_context=h.inference_context,
                source=h.source,
            )
            for h in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.patch(
    "/{project_id}/findings/batch",
    response_model=BatchPatchResponse,
)
async def batch_patch_findings(
    project_id: int,
    request: Request,
    body: BatchFindingPatchRequest,
) -> BatchPatchResponse:
    """Apply analyst field updates to multiple findings in one request.

    Locked findings are skipped (not errored). Returns three disjoint
    id buckets: updated, skipped_locked, not_found.
    """
    service = _service(request, project_id)
    raw = body.model_dump(exclude={"ids"}, exclude_none=True)
    fields = _translate_patch_fields(raw)

    result = await asyncio.to_thread(service.batch_patch_findings, body.ids, fields)
    return BatchPatchResponse(
        updated=result.updated,
        skipped_locked=result.skipped_locked,
        not_found=result.not_found,
        skip_reasons=result.skip_reasons,
    )


@v1_router.patch(
    "/{project_id}/findings/{finding_id}",
    response_model=FindingResponse,
)
async def patch_finding(
    project_id: int,
    finding_id: int,
    request: Request,
    body: FindingPatchRequest,
) -> dict:
    """Update analyst-editable fields on a finding.

    Returns 409 if locked; 404 if not found. Syncs metadata to ChromaDB
    after the write.
    """
    service = _service(request, project_id)
    raw = body.model_dump(exclude_none=True)
    fields = _translate_patch_fields(raw)

    try:
        finding = await asyncio.to_thread(service.patch_finding, finding_id, fields)
    except FindingsBusy as exc:
        raise FindingsLocked(exc.conflicting_ids, exc.holders) from exc

    if finding is None:
        raise NotFound("Finding not found")

    return _serialise_finding(finding, service.lock_state_for(finding.id))

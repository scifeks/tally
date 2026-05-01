"""Project-scoped findings endpoints (GET, PATCH, SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.findings.analyst_service import FindingAnalystService
from application.locking import FindingsBusy, LockQueryService
from core.project_paths import ProjectPaths
from domain.findings.severity import Severity
from domain.findings.sort import FindingSortColumn, SortDirection
from infrastructure.events.ids import new_event_id
from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import BusEvent
from infrastructure.store import FindingRepository
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.finding_history import FindingHistoryRepository
from web.api._errors import FindingsLocked, NotFound
from web.api._project_resolver import _resolve_project
from web.api.chroma_sync import sync_finding_to_chroma
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
)

logger = logging.getLogger("tally.web.findings")

# Kept empty for backward-compat imports — routes are on v1_router.
router = APIRouter()

# Matches type_secret, type_vulnerability, type_weakness, etc.
_TYPE_FLAG_RE = re.compile(r"^type_[a-z]+$")


def _serialise_finding(row: dict[str, Any]) -> dict[str, Any]:
    """Serialise a raw SQLite findings row for the API response.

    Steps applied:
    - Parse the ``meta`` JSON blob to a dict; strip all ``type_*`` flags.
    - Parse ``finding_type`` and ``cwe`` JSON array strings to lists.
    - Translate severity integer rank to label.
    - Expose the named ``fingerprint`` column as ``id_fingerprint`` to avoid
      collision with semgrep's scanner fingerprint stored in ``meta``.
    - Annotate ``is_locked`` and ``lock_holder`` from the live registry.
    """
    result: dict[str, Any] = dict(row)

    # Parse meta JSON blob.
    try:
        meta: dict[str, Any] = json.loads(result.get("meta") or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}

    # Strip ChromaDB-only type_* flags.
    meta = {k: v for k, v in meta.items() if not _TYPE_FLAG_RE.match(k)}
    result["meta"] = meta

    # Parse finding_type JSON array string → list.
    ft_raw = result.get("finding_type")
    if ft_raw:
        try:
            result["finding_type"] = json.loads(ft_raw)
        except (json.JSONDecodeError, TypeError):
            result["finding_type"] = []
    else:
        result["finding_type"] = []

    # Parse cwe JSON array string → list.
    cwe_raw = result.get("cwe")
    if cwe_raw:
        try:
            result["cwe"] = json.loads(cwe_raw)
        except (json.JSONDecodeError, TypeError):
            result["cwe"] = []
    else:
        result["cwe"] = []

    # Translate severity integer rank to label (search_raw returns raw ranks).
    sev_raw = result.get("severity")
    if isinstance(sev_raw, int):
        result["severity"] = Severity.from_rank(sev_raw).label

    # Rename named fingerprint column to id_fingerprint.
    result["id_fingerprint"] = result.pop("fingerprint", None)

    # Annotate live lock state from the registry.
    finding_id: int | None = result.get("id")
    if finding_id is not None:
        svc = LockQueryService()
        result["is_locked"] = svc.is_finding_locked(finding_id)
        result["lock_holder"] = svc.finding_lock_holder(finding_id)
    else:
        result["is_locked"] = False
        result["lock_holder"] = None

    return result


def _make_repo(row: dict) -> FindingRepository:
    """Build a FindingRepository for the project described by *row*."""
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    return FindingRepository(factory)


def _make_history_repo(row: dict) -> FindingHistoryRepository:
    """Build a FindingHistoryRepository for the project described by *row*."""
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    return FindingHistoryRepository(factory)


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
    row = _resolve_project(request, project_id)
    repo = _make_repo(row)
    service = FindingAnalystService(repo)
    data = await asyncio.to_thread(service.count_aggregates)
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
    row = _resolve_project(request, project_id)
    repo = _make_repo(row)
    service = FindingAnalystService(repo)
    data = await asyncio.to_thread(service.distinct_facet_values)
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
    """Return per-dimension filter options under the active filter set.

    Mirrors the filter query params of ``GET /findings``. Each dimension's
    counts apply every active filter (strict semantics) and zero-count
    options are omitted. Powers the Findings page filter dropdowns
    (Phase 12.1).
    """
    row = _resolve_project(request, project_id)

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

    repo_obj = _make_repo(row)
    service = FindingAnalystService(repo_obj)
    data = await asyncio.to_thread(service.filter_options, filters)
    return FindingsFilterOptionsResponse(**data)


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

    ``repo_id`` (integer DB id) is the canonical repo filter.
    Each response item carries both ``repo_id`` and ``repo_name`` so
    callers don't have to JOIN client-side.
    """
    row = _resolve_project(request, project_id)

    # Validate severity labels — ValueError → 422 via global handler.
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

    repo_obj = _make_repo(row)
    service = FindingAnalystService(repo_obj)
    total = await asyncio.to_thread(service.search_count, filters)
    rows = await asyncio.to_thread(service.search_raw, filters)

    repo_name_by_id = _repo_name_lookup(row)
    items: list[FindingResponse] = []
    for r in rows:
        serial = _serialise_finding(r)
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


def _repo_name_lookup(project_row: dict) -> dict[int, str]:
    """Build a ``{repo_id: repo_name}`` map for a project's active repos."""
    try:
        from infrastructure.store.repositories.repositories import (
            RepositoryRepository,
        )

        paths = ProjectPaths.from_registry_row(project_row)
        if not paths.findings_db.exists():
            return {}
        factory = ConnectionFactory(paths.findings_db)
        repo_repo = RepositoryRepository(factory)
        return {
            r.id: r.name
            for r in repo_repo.list_active()
            if r.name and isinstance(r.id, int)
        }
    except Exception:
        return {}


@v1_router.get("/{project_id}/findings/events")
async def findings_events(
    project_id: int,
    request: Request,
) -> StreamingResponse:
    """SSE stream emitting finding_updated events for this project.

    Tail-only — no snapshot on connect. Clients filter by event_type.
    Each event carries the full serialised finding record plus project_id.
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
                from infrastructure.events.types import EOS

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
    row = _resolve_project(request, project_id)
    repo = _make_repo(row)
    service = FindingAnalystService(repo)
    finding = await asyncio.to_thread(service.get_finding, finding_id)
    if finding is None:
        raise NotFound("Finding not found")
    return _serialise_finding(finding)


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
    row = _resolve_project(request, project_id)
    repo = _make_repo(row)
    service = FindingAnalystService(repo)
    finding = await asyncio.to_thread(service.get_finding, finding_id)
    if finding is None:
        raise NotFound("Finding not found")
    history_repo = _make_history_repo(row)
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

    Locked findings are skipped (not errored). Returns three disjoint id
    buckets: updated, skipped_locked, not_found.
    """
    row = _resolve_project(request, project_id)
    repo = _make_repo(row)
    service = FindingAnalystService(repo)

    session_id: str = request.state.session_id
    holder = f"analyst-patch:web:{session_id[:8]}"

    raw = body.model_dump(exclude={"ids"}, exclude_none=True)
    fields: dict[str, Any] = {}
    for k, v in raw.items():
        if k == "should_report":
            fields["should_report"] = 1 if v else 0
        else:
            fields[k] = v

    result = await asyncio.to_thread(
        service.bulk_update_fields, body.ids, fields, holder_token=holder
    )

    # Emit finding_updated for each successfully updated finding.
    bus = request.app.state.event_bus
    for fid in result.updated:
        updated_row = await asyncio.to_thread(service.get_finding, fid)
        if updated_row is not None:
            serialised = _serialise_finding(updated_row)
            await bus.publish(
                BusEvent(
                    event_id=new_event_id(),
                    job_id="finding",
                    stream="finding",
                    event_type="finding_updated",
                    payload={**serialised, "project_id": project_id},
                    ts=datetime.now(UTC),
                )
            )

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
    """Apply analyst corrections to a finding's editable fields.

    Only fields explicitly included in the request body are written.
    Returns 409 FINDING_LOCKED if the finding is held by another job.
    Returns 404 if the finding does not exist.
    After the SQLite write, performs a best-effort ChromaDB metadata sync.
    """
    row = _resolve_project(request, project_id)
    repo = _make_repo(row)
    service = FindingAnalystService(repo)

    session_id: str = request.state.session_id
    holder = f"analyst-patch:web:{session_id[:8]}"

    raw = body.model_dump(exclude_none=True)
    fields: dict[str, Any] = {}
    for k, v in raw.items():
        if k.startswith("meta_"):
            fields[k.removeprefix("meta_")] = v
        elif k == "finding_type":
            fields["finding_type"] = json.dumps(v)
        elif k == "cwe":
            fields["cwe"] = json.dumps(v)
        elif k == "should_report":
            fields["should_report"] = 1 if v else 0
        else:
            fields[k] = v

    try:
        updated = await asyncio.to_thread(
            service.update_fields, finding_id, fields, holder_token=holder
        )
    except FindingsBusy as exc:
        raise FindingsLocked(exc.conflicting_ids, exc.holders) from exc

    if not updated:
        raise NotFound("Finding not found")

    finding = await asyncio.to_thread(service.get_finding, finding_id)
    if finding is None:
        raise NotFound("Finding not found")

    serialised = _serialise_finding(finding)
    from web.server import get_knowledge_base

    knowledge_base = get_knowledge_base(
        request.app, row["name"], request.app.state.base_path
    )
    sync_finding_to_chroma(
        finding_id=finding_id,
        knowledge_base=knowledge_base,
        finding_repo=repo,
    )

    bus = request.app.state.event_bus
    await bus.publish(
        BusEvent(
            event_id=new_event_id(),
            job_id="finding",
            stream="finding",
            event_type="finding_updated",
            payload={**serialised, "project_id": project_id},
            ts=datetime.now(UTC),
        )
    )

    return serialised

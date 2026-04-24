"""GET and PATCH /api/findings endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Query, Request

from application.findings.analyst_service import FindingAnalystService
from application.locking import FindingsBusy, LockQueryService
from infrastructure.store import FindingRepository
from web.api._errors import FindingsLocked, NotFound
from web.api.chroma_sync import sync_finding_to_chroma
from web.api.schemas import (
    BatchFindingPatchRequest,
    BatchPatchResponse,
    FindingPatchRequest,
    FindingResponse,
    FindingsListResponse,
)

logger = logging.getLogger("tally.web.findings")

router = APIRouter()

# Matches type_secret, type_vulnerability, type_weakness, etc.
_TYPE_FLAG_RE = re.compile(r"^type_[a-z]+$")


def _serialise_finding(row: dict[str, Any]) -> dict[str, Any]:
    """Serialise a raw SQLite findings row for the API response.

    Steps applied:
    - Parse the ``meta`` JSON blob to a dict; strip all ``type_*`` flags.
    - Parse ``finding_type`` and ``cwe`` JSON array strings to lists.
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


@router.get("/", response_model=FindingsListResponse)
def list_findings(
    request: Request,
    tool: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    status: str | None = Query(default=None),
    segment: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> FindingsListResponse:
    """Return findings with pagination envelope."""
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)
    service = FindingAnalystService(repo)
    tools = [tool] if tool else None
    segments = [segment] if segment else None
    total = service.count_findings(
        tools=tools,
        domain=domain,
        status=status,
        segments=segments,
    )
    rows = service.get_findings(
        tools=tools,
        domain=domain,
        status=status,
        segments=segments,
        offset=offset,
        limit=limit,
    )
    return FindingsListResponse(
        items=[FindingResponse.model_validate(_serialise_finding(r)) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{finding_id}", response_model=FindingResponse)
def get_finding(request: Request, finding_id: int) -> dict:
    """Return a single finding by integer primary key."""
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)
    service = FindingAnalystService(repo)
    row = service.get_finding(finding_id)
    if row is None:
        raise NotFound("Finding not found")
    return _serialise_finding(row)


@router.patch("/batch", response_model=BatchPatchResponse)
async def batch_patch_findings(
    request: Request,
    body: BatchFindingPatchRequest,
) -> BatchPatchResponse:
    """Apply analyst field updates to multiple findings in one request.

    Locked findings are skipped (not errored). Returns three disjoint id
    buckets: updated, skipped_locked, not_found.
    """
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)
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
    return BatchPatchResponse(
        updated=result.updated,
        skipped_locked=result.skipped_locked,
        not_found=result.not_found,
        skip_reasons=result.skip_reasons,
    )


@router.patch("/{finding_id}", response_model=FindingResponse)
async def patch_finding(
    request: Request,
    finding_id: int,
    body: FindingPatchRequest,
) -> dict:
    """Apply analyst corrections to a finding's editable fields.

    Only fields explicitly included in the request body are written.
    Returns 409 FINDING_LOCKED if the finding is held by another job.
    Returns 404 if the finding does not exist.
    After the SQLite write, performs a best-effort ChromaDB metadata sync.
    """
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)
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

    row = service.get_finding(finding_id)
    if row is None:
        raise NotFound("Finding not found")

    serialised = _serialise_finding(row)
    sync_finding_to_chroma(
        finding_id=finding_id,
        rag_engine=request.app.state.rag_engine,
        finding_repo=repo,
    )
    return serialised

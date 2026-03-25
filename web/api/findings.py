"""GET and PATCH /api/findings endpoints."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from infrastructure.store import FindingRepository
from web.api.schemas import FindingPatchRequest

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

    return result


@router.get("/")
def list_findings(
    request: Request,
    tool: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    status: str | None = Query(default=None),
    segment: str | None = Query(default=None),
) -> list[dict]:
    """Return findings, optionally filtered by tool, domain, status, or segment."""
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)
    rows = repo.get_findings(
        tools=[tool] if tool else None,
        domain=domain,
        status=status,
        segments=[segment] if segment else None,
        limit=10_000,
    )
    return [_serialise_finding(r) for r in rows]


@router.get("/{finding_id}")
def get_finding(request: Request, finding_id: int) -> dict:
    """Return a single finding by integer primary key."""
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)
    row = repo.get_finding(finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _serialise_finding(row)


# Maps FindingPatchRequest field names for meta keys to their blob keys.
_META_FIELD_MAP: dict[str, str] = {
    "meta_remediation": "remediation",
    "meta_risk_type": "risk_type",
    "meta_owasp_name": "owasp_name",
    "meta_title": "title",
    "meta_tags": "tags",
}


@router.patch("/{finding_id}")
def patch_finding(
    request: Request,
    finding_id: int,
    body: FindingPatchRequest,
) -> dict:
    """Apply analyst corrections to a finding's editable fields.

    Only fields explicitly included in the request body are written.
    Locked fields sent by the client are silently ignored.
    Sets ``triaged_by = 'analyst_web'`` and ``triaged_at = now()`` on
    every successful write.

    Returns the updated finding on success, or 404 if not found.
    Chroma sync is NOT performed in this step (deferred to Prompt 03).
    """
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)

    raw = body.model_dump(exclude_none=True)

    fields: dict[str, Any] = {}
    for k, v in raw.items():
        if k in _META_FIELD_MAP:
            fields[_META_FIELD_MAP[k]] = v
        elif k == "finding_type":
            fields["finding_type"] = json.dumps(v)
        elif k == "cwe":
            fields["cwe"] = json.dumps(v)
        elif k == "should_report":
            fields["should_report"] = 1 if v else 0
        else:
            fields[k] = v

    updated = repo.update_analyst_fields(finding_id, fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Finding not found")

    row = repo.get_finding(finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _serialise_finding(row)

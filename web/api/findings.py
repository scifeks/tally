"""GET /api/findings and GET /api/findings/{id} endpoints."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from infrastructure.store import FindingRepository

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

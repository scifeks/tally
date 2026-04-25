"""GET /api/v1/projects/{project_id}/locks endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from application.locking import LockQueryService
from web.api._errors import NotFound

router = APIRouter()


@router.get("/{project_id}/locks")
def list_project_locks(project_id: int, request: Request) -> dict:
    """Return current lock state for the given project."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.get("archived_at"):
        raise NotFound(f"Project {project_id} not found")

    svc = LockQueryService()
    jobs_snap, findings_snap = svc.snapshot()

    finding_locks = [
        {"id": fid, "holder": holder} for fid, holder in sorted(findings_snap.items())
    ]
    job_locks = {
        "scan": jobs_snap.get("scan"),
        "triage": jobs_snap.get("triage"),
        "report": jobs_snap.get("report"),
    }
    return {
        "project_id": project_id,
        "finding_locks": finding_locks,
        "job_locks": job_locks,
    }

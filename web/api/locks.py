"""GET /api/v1/projects/{project_id}/locks endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from application.locking import get_registry

router = APIRouter()


@router.get("/{project_id}/locks")
def list_project_locks(project_id: str) -> dict:
    """Return current lock state for the active project.

    Registry is process-global (single-user); ``project_id`` is accepted for
    forward-compatibility with endpoints.md §4 but echoed in the response body
    until per-project filtering is implemented.
    """
    registry = get_registry()
    jobs_snap, findings_snap = registry.snapshot()

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

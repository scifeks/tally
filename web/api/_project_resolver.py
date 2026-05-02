"""Shared project resolver for web API handlers."""

from __future__ import annotations

from fastapi import Request

from domain.projects.entry import ProjectRow
from web.api._errors import NotFound


def _resolve_project(request: Request, project_id: int) -> ProjectRow:
    """Resolve a project_id via registry; raise NotFound if missing/archived."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise NotFound(f"Project {project_id} not found")
    return row

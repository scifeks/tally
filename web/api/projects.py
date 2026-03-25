"""GET /api/projects — active project context."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
def get_project(request: Request) -> dict:
    """Return the active project name and SQLite database path."""
    project_name: str = request.app.state.project_name
    base_path: str = request.app.state.base_path
    sqlite_path = str(
        Path(base_path) / "projects" / project_name / "sqlite" / "findings.db"
    )
    return {"project_name": project_name, "sqlite_path": sqlite_path}

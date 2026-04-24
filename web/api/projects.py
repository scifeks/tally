"""Project API endpoints — stub and v1 versioned routes."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from application.project.manager import ProjectManager
from infrastructure.store.connection import ConnectionFactory
from web.api._errors import NotFound
from web.api.schemas import (
    ProjectInfoResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectMetaResponse,
    RepositoryListResponse,
)

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


# ---------------------------------------------------------------------------
# v1 router
# ---------------------------------------------------------------------------

v1_router = APIRouter()


async def _count_findings(request: Request, project_name: str) -> int:
    if project_name == request.app.state.project_name:
        factory = request.app.state.connection_factory
    else:
        db_path = (
            Path(request.app.state.base_path)
            / "projects"
            / project_name
            / "sqlite"
            / "findings.db"
        )
        if not db_path.exists():
            return 0
        factory = ConnectionFactory(db_path)

    def _query(f: ConnectionFactory) -> int:
        try:
            with f.connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM findings").fetchone()
                return row[0]
        except Exception:
            return 0

    return await asyncio.to_thread(_query, factory)


@v1_router.get("/", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> ProjectListResponse:
    base_path: str = request.app.state.base_path
    active: str = request.app.state.project_name
    manager = ProjectManager(base_path)
    all_names = manager.list_projects()
    items: list[ProjectListItem] = []
    for name in all_names:
        config = manager.get_project_info(name)
        if config is None:
            continue
        items.append(
            ProjectListItem(
                id=name,
                name=config.project_name,
                code=config.abbreviation,
                created_at=config.created,
                is_active=(name == active),
            )
        )
    total = len(items)
    return ProjectListResponse(
        items=items[offset : offset + limit],
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.get("/{project_name}/meta", response_model=ProjectMetaResponse)
async def get_project_meta(
    project_name: str,
    request: Request,
) -> ProjectMetaResponse:
    base_path: str = request.app.state.base_path
    manager = ProjectManager(base_path)
    config = manager.get_project_info(project_name)
    if config is None:
        raise NotFound(f"Project '{project_name}' not found")
    finding_count = await _count_findings(request, project_name)
    return ProjectMetaResponse(
        id=project_name,
        name=config.project_name,
        code=config.abbreviation,
        repo_count=len(config.repositories),
        url_list_count=0,
        finding_count=finding_count,
    )


@v1_router.get("/{project_name}/info", response_model=ProjectInfoResponse)
async def get_project_info_endpoint(
    project_name: str,
    request: Request,
) -> ProjectInfoResponse:
    base_path: str = request.app.state.base_path
    manager = ProjectManager(base_path)
    config = manager.get_project_info(project_name)
    if config is None:
        raise NotFound(f"Project '{project_name}' not found")
    finding_count = await _count_findings(request, project_name)
    return ProjectInfoResponse(
        id=project_name,
        name=config.project_name,
        code=config.abbreviation,
        company=config.company_name,
        department=config.department_name,
        abbreviation=config.abbreviation,
        created_at=config.created,
        path=str(Path(base_path) / "projects" / project_name),
        repo_count=len(config.repositories),
        finding_count=finding_count,
    )


@v1_router.get(
    "/{project_name}/repositories",
    response_model=RepositoryListResponse,
)
async def list_repositories(
    project_name: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> JSONResponse:
    base_path: str = request.app.state.base_path
    manager = ProjectManager(base_path)
    config = manager.get_project_info(project_name)
    if config is None:
        raise NotFound(f"Project '{project_name}' not found")
    repos = config.repositories
    total = len(repos)
    page = repos[offset : offset + limit]
    items = []
    for repo in page:
        data = repo.model_dump()
        data.pop("auth", None)
        items.append(data)
    return JSONResponse(
        content={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )

"""Project API endpoints — stub and v1 versioned routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from application.project.manager import ProjectManager
from core.project_paths import ProjectPaths
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
    paths = ProjectPaths.from_canonical(base_path, project_name)
    return {"project_name": project_name, "sqlite_path": str(paths.findings_db)}


# ---------------------------------------------------------------------------
# v1 router
# ---------------------------------------------------------------------------

v1_router = APIRouter()


def _resolve_project(request: Request, project_id: int) -> dict:
    """Resolve a project_id via registry; raise NotFound if missing/archived."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.get("archived_at"):
        raise NotFound(f"Project {project_id} not found")
    return row


async def _count_findings(
    request: Request, project_name: str, paths: ProjectPaths
) -> int:
    if project_name == request.app.state.project_name:
        factory = request.app.state.connection_factory
    elif not paths.findings_db.exists():
        return 0
    else:
        factory = ConnectionFactory(paths.findings_db)

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
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    items: list[ProjectListItem] = []
    for row in registry.list_active():
        config = manager.get_project_info(row["name"])
        if config is None:
            continue
        items.append(
            ProjectListItem(
                id=int(row["id"]),
                name=config.project_name,
                code=config.abbreviation,
                created_at=config.created,
                is_active=(row["name"] == active),
            )
        )
    total = len(items)
    return ProjectListResponse(
        items=items[offset : offset + limit],
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.get("/{project_id}/meta", response_model=ProjectMetaResponse)
async def get_project_meta(
    project_id: int,
    request: Request,
) -> ProjectMetaResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    finding_count = await _count_findings(request, row["name"], paths)
    return ProjectMetaResponse(
        id=int(row["id"]),
        name=config.project_name,
        code=config.abbreviation,
        repo_count=len(config.repositories),
        url_list_count=0,
        finding_count=finding_count,
    )


@v1_router.get("/{project_id}/info", response_model=ProjectInfoResponse)
async def get_project_info_endpoint(
    project_id: int,
    request: Request,
) -> ProjectInfoResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    finding_count = await _count_findings(request, row["name"], paths)
    return ProjectInfoResponse(
        id=int(row["id"]),
        name=config.project_name,
        code=config.abbreviation,
        company=config.company_name,
        department=config.department_name,
        abbreviation=config.abbreviation,
        created_at=config.created,
        path=str(paths.root),
        repo_count=len(config.repositories),
        finding_count=finding_count,
    )


@v1_router.get(
    "/{project_id}/repositories",
    response_model=RepositoryListResponse,
)
async def list_repositories(
    project_id: int,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> JSONResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")
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

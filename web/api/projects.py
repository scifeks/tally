"""Project API endpoints, v1 versioned routes.

The server is project-agnostic: ``/api/v1/projects`` returns the full
project list (auth-only); per-project routes resolve their target via
the path ``:project_id`` and the project registry.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from application.findings.findings_service import (
    FindingsService,
)
from application.findings.findings_service import (
    ProjectNotFound as FindingsProjectNotFound,
)
from application.project.manager import ProjectManager
from application.project.repositories_service import (
    DuplicateRepositoryName,
    ProjectRepositoriesService,
    RepositoryNotFound,
)
from application.url_inventory.url_list_service import (
    ProjectNotFound as UrlListProjectNotFound,
)
from application.url_inventory.url_list_service import (
    UrlListService,
)
from core.config.manager import ConfigManager
from core.config.schemas import Repository
from core.project_paths import ProjectPaths
from domain.projects.entry import ProjectRow
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.tool_overrides import (
    ToolOverridesRepository,
)
from web.api._errors import NotFound
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    ProjectInfoPatchRequest,
    ProjectInfoResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectMetaResponse,
    RepoAuthPatchRequest,
    RepositoryItem,
    RepositoryListResponse,
)

# v1 router
v1_router = APIRouter()


def _findings_service(request: Request, project_id: int) -> FindingsService:
    """Build a FindingsService for *project_id* or raise 404."""
    try:
        return FindingsService.for_project(
            request.app.state.project_registry, project_id
        )
    except FindingsProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _url_list_service(request: Request, project_id: int) -> UrlListService:
    """Build a UrlListService for *project_id* or raise 404."""
    try:
        return UrlListService.for_project(
            request.app.state.project_registry, project_id
        )
    except UrlListProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _load_project_tool_ids(paths: ProjectPaths) -> list[str]:
    """Return sorted tool names from tool_overrides table in DB."""
    factory = ConnectionFactory(paths.findings_db)
    repo = ToolOverridesRepository(factory)
    rows, _total = repo.list_paginated(offset=0, limit=10_000)
    return sorted(o.tool_name for o in rows)


def _service_from_request(request: Request) -> ProjectRepositoriesService:
    return ProjectRepositoriesService.build(
        request.app.state.project_registry,
        request.app.state.base_path,
    )


def _count_active_repos(service: ProjectRepositoriesService, project_id: int) -> int:
    return len(service.list_active(project_id))


@v1_router.get("", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> ProjectListResponse:
    """Return the full project list (auth-only).

    The SPA uses this to populate the project picker before any
    project is selected. No project context required.
    """
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    items: list[ProjectListItem] = []
    for row in registry.list_active():
        config = manager.get_project_info(row.name)
        if config is None:
            continue
        items.append(
            ProjectListItem(
                id=row.id,
                name=config.project_name,
                code=config.abbreviation,
                created_at=config.created,
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
    config = manager.get_project_info(row.name)
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)

    findings_service = _findings_service(request, project_id)
    url_list_service = _url_list_service(request, project_id)
    finding_count = await asyncio.to_thread(findings_service.count_findings)
    url_list_count = await asyncio.to_thread(url_list_service.count_active_url_findings)
    enabled_tools = await asyncio.to_thread(_load_project_tool_ids, paths)
    repo_service = _service_from_request(request)
    repo_count = await asyncio.to_thread(_count_active_repos, repo_service, project_id)
    return ProjectMetaResponse(
        id=row.id,
        name=config.project_name,
        code=config.abbreviation,
        repo_count=repo_count,
        url_list_count=url_list_count,
        finding_count=finding_count,
        enabled_tools=enabled_tools,
    )


def _build_project_info_response(
    row: ProjectRow,
    config,
    finding_count: int,
    repo_count: int,
) -> ProjectInfoResponse:
    paths = ProjectPaths.from_registry_row(row)
    return ProjectInfoResponse(
        id=row.id,
        name=config.project_name,
        code=config.abbreviation,
        company_name=config.company_name,
        department_name=config.department_name,
        abbreviation=config.abbreviation,
        created_at=config.created,
        path=str(paths.root),
        repo_count=repo_count,
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
    config = manager.get_project_info(row.name)
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    findings_service = _findings_service(request, project_id)
    finding_count = await asyncio.to_thread(findings_service.count_findings)
    repo_service = _service_from_request(request)
    repo_count = await asyncio.to_thread(_count_active_repos, repo_service, project_id)
    return _build_project_info_response(row, config, finding_count, repo_count)


@v1_router.patch("/{project_id}/info", response_model=ProjectInfoResponse)
async def patch_project_info(
    project_id: int,
    request: Request,
    body: ProjectInfoPatchRequest,
) -> ProjectInfoResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    project_name = row.name
    manager = ConfigManager(base_path)

    update: dict[str, str] = {}
    for field in ("company_name", "department_name", "abbreviation"):
        value = getattr(body, field)
        if value is not None:
            update[field] = value

    with manager.locked_project_config(project_name):
        config = manager.load_project_config(project_name)
        if config is None:
            raise NotFound(f"Project {project_id} not found")
        if update:
            config = config.model_copy(update=update)
            manager.save_project_config(project_name, config)

    findings_service = _findings_service(request, project_id)
    finding_count = await asyncio.to_thread(findings_service.count_findings)
    repo_service = _service_from_request(request)
    repo_count = await asyncio.to_thread(_count_active_repos, repo_service, project_id)
    return _build_project_info_response(row, config, finding_count, repo_count)


def _existing_endpoint_file(repo: Repository) -> str | None:
    """Return the basename of the repo's most-recent seed-file upload, or
    ``None`` if no seed file is configured.

    The path is persisted in ``repositories.url_seed_file`` and points
    at ``endpoints/<repo-name>-<epoch>/<basename>``.
    """
    if not repo.url_seed_file:
        return None
    return Path(repo.url_seed_file).name


def _serialize_repo(repo: Repository, repo_id: int | None) -> dict:
    """Dump a Repository to a JSON dict; strip auth; carry id and seed file."""
    data = repo.model_dump()
    data.pop("auth", None)
    data["id"] = repo_id
    data["endpoint_file"] = _existing_endpoint_file(repo)
    return data


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
    _resolve_project(request, project_id)
    service = _service_from_request(request)
    repos = service.list_active(project_id)
    total = len(repos)
    page = repos[offset : offset + limit]
    items = [_serialize_repo(repo, repo.id) for repo in page]
    return JSONResponse(
        content={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )


@v1_router.get(
    "/{project_id}/repositories/{repo_id}",
    response_model=RepositoryItem,
)
async def get_repository_detail(
    project_id: int,
    repo_id: int,
    request: Request,
) -> JSONResponse:
    """Return a single repository. Auth fields are never echoed."""
    _resolve_project(request, project_id)
    service = _service_from_request(request)
    try:
        repo = service.get(project_id, repo_id)
    except RepositoryNotFound as exc:
        raise NotFound(str(exc)) from exc
    return JSONResponse(content=_serialize_repo(repo, repo.id))


def _parse_payload(payload: str | None) -> dict[str, Any]:
    """Parse a multipart-form ``payload`` JSON string into a dict."""
    if payload is None or payload == "":
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ApiValidationError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ApiValidationError("Payload must be a JSON object")
    return data


@v1_router.post("/{project_id}/repositories", status_code=201)
async def create_repository(
    project_id: int,
    request: Request,
    payload: str = Form(...),
    endpoint_file: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Create a new repository (multipart)."""
    _resolve_project(request, project_id)

    data = _parse_payload(payload)
    data.pop("id", None)

    try:
        repo = Repository(**data)
    except ValidationError as exc:
        raise ApiValidationError(str(exc)) from exc

    service = _service_from_request(request)
    try:
        created = service.create(project_id, repo)
    except DuplicateRepositoryName as exc:
        raise ApiValidationError(str(exc)) from exc

    if endpoint_file is not None and endpoint_file.filename and created.id is not None:
        await _ingest_endpoint_file(request, project_id, created, endpoint_file)
        created = service.get(project_id, created.id)

    return JSONResponse(status_code=201, content=_serialize_repo(created, created.id))


@v1_router.patch("/{project_id}/repositories/{repo_id}")
async def patch_repository(
    project_id: int,
    repo_id: int,
    request: Request,
    payload: str | None = Form(default=None),
    endpoint_file: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Partial update of a repository (multipart)."""
    _resolve_project(request, project_id)
    service = _service_from_request(request)

    data = _parse_payload(payload)
    data.pop("id", None)

    try:
        updated = service.update(project_id, repo_id, data)
    except RepositoryNotFound as exc:
        raise NotFound(str(exc)) from exc
    except DuplicateRepositoryName as exc:
        raise ApiValidationError(str(exc)) from exc
    except ValidationError as exc:
        raise ApiValidationError(str(exc)) from exc

    if endpoint_file is not None and endpoint_file.filename:
        await _ingest_endpoint_file(request, project_id, updated, endpoint_file)
        updated = service.get(project_id, repo_id)

    return JSONResponse(content=_serialize_repo(updated, updated.id))


@v1_router.delete("/{project_id}/repositories/{repo_id}", status_code=204)
async def delete_repository(
    project_id: int,
    repo_id: int,
    request: Request,
) -> Response:
    """Soft-delete a repository."""
    _resolve_project(request, project_id)
    service = _service_from_request(request)
    try:
        service.delete(project_id, repo_id)
    except RepositoryNotFound as exc:
        raise NotFound(str(exc)) from exc
    return Response(status_code=204)


@v1_router.patch(
    "/{project_id}/repositories/{repo_id}/auth",
    status_code=204,
)
async def patch_repository_auth(
    project_id: int,
    repo_id: int,
    request: Request,
    body: RepoAuthPatchRequest,
) -> Response:
    """Update the auth block on a repository (JSON). Auth is never echoed."""
    _resolve_project(request, project_id)
    service = _service_from_request(request)
    auth_patch = body.model_dump(exclude_none=True)
    try:
        service.update_auth(project_id, repo_id, auth_patch)
    except RepositoryNotFound as exc:
        raise NotFound(str(exc)) from exc
    except ValidationError as exc:
        raise ApiValidationError(str(exc)) from exc
    return Response(status_code=204)


async def _ingest_endpoint_file(
    request: Request,
    project_id: int,
    repo: Repository,
    endpoint_file: UploadFile,
) -> None:
    """Read the upload off the request and hand it to the URL list service."""
    if repo.id is None:
        raise ApiValidationError("Repository must be persisted before upload")
    contents = await endpoint_file.read()
    filename = endpoint_file.filename or "upload.json"
    service = _url_list_service(request, project_id)
    await asyncio.to_thread(
        service.ingest_uploaded_endpoint_file,
        repo=repo,
        repo_id=repo.id,
        filename=filename,
        contents=contents,
    )

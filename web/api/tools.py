"""Tool catalog and tool override read endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Query, Request, Response

from application.ports.tool_overrides import (
    ToolOverrideNameConflict,
    ToolOverridesRepositoryPort,
)
from application.runtime.dependency_service import RuntimeDependencyService
from application.tool_overrides.service import (
    ToolOverrideNotFound,
    ToolOverridesService,
    ToolOverrideValidationError,
)
from core.project_paths import ProjectPaths
from factories.persistence import create_overrides_repo
from web.api._errors import Conflict, NotFound
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    InstalledToolsResponse,
    RuntimeDependenciesResponse,
    RuntimeDependencyItem,
    ToolCatalogItem,
    ToolCatalogResponse,
)
from web.api.tool_overrides_schemas import (
    ToolOverrideContainerResponse,
    ToolOverrideCreateRequest,
    ToolOverrideListResponse,
    ToolOverrideReplaceRequest,
    ToolOverrideResponse,
)

_WRAPPERS_ROOT = (
    Path(__file__).parent.parent.parent / "infrastructure" / "tools" / "wrappers"
)

tools_v1_router = APIRouter()
projects_tools_v1_router = APIRouter()
runtime_v1_router = APIRouter()


@runtime_v1_router.get(
    "/runtime-dependencies",
    response_model=RuntimeDependenciesResponse,
)
def get_runtime_dependencies(request: Request) -> RuntimeDependenciesResponse:
    """Return cached probe status for all registered runtime dependencies."""
    service: RuntimeDependencyService = request.app.state.runtime_dependency_service
    deps = [
        RuntimeDependencyItem(
            name=s.name,
            installed=s.installed,
            binary_path=s.binary_path,
            version=s.version,
            install_hint=s.install_hint,
            required_for=list(s.required_for),
            error=s.error,
        )
        for s in service.statuses()
    ]
    return RuntimeDependenciesResponse(dependencies=deps)


def _supports_local(tool_name: str) -> bool:
    normalized = tool_name.replace("-", "_")
    return (_WRAPPERS_ROOT / "local" / f"{normalized}.py").exists()


def _supports_docker(tool_name: str) -> bool:
    normalized = tool_name.replace("-", "_")
    return (_WRAPPERS_ROOT / "docker" / f"{normalized}.py").exists()


def _discover_all_tool_names() -> set[str]:
    """Scan wrapper directories for all tools with implementations."""
    names: set[str] = set()
    for subdir in ("local", "docker"):
        d = _WRAPPERS_ROOT / subdir
        if not d.is_dir():
            continue
        for p in d.glob("*.py"):
            if p.stem.startswith("_"):
                continue
            names.add(p.stem.replace("_", "-"))
    return names


def _build_service(
    request: Request, project_id: int
) -> tuple[ToolOverridesService, ToolOverridesRepositoryPort, ProjectPaths, str]:
    row = _resolve_project(request, project_id)
    paths = ProjectPaths.from_registry_row(row)
    repo = create_overrides_repo(paths.findings_db)
    return ToolOverridesService(repo), repo, paths, row.name


def _to_response(override) -> ToolOverrideResponse:
    container = None
    if override.container_name and override.container_tool_path:
        container = ToolOverrideContainerResponse(
            name=override.container_name,
            tool_path=override.container_tool_path,
        )
    return ToolOverrideResponse(
        id=override.id,
        tool_name=override.tool_name,
        args_mode=override.args_mode,
        type=override.type,
        location=override.location,
        path=override.path,
        container=container,
    )


@tools_v1_router.get("/catalog", response_model=ToolCatalogResponse)
def get_tools_catalog(request: Request) -> ToolCatalogResponse:
    """Return metadata for all registered tool wrappers.

    Reads from the startup snapshot so that per-project
    ``discover_tools`` calls (scans, saved-scan runs) cannot shrink
    the catalog that the Config page sees.
    """
    tools_dict, _configs = request.app.state.tool_catalog_snapshot
    tools = list(tools_dict.values())
    items = [
        ToolCatalogItem(
            id=tool.name,
            name=tool.name.replace("_", " ").replace("-", " ").title(),
            domain=tool.category,
            supports_local=_supports_local(tool.name),
            supports_docker=_supports_docker(tool.name),
            description=tool.description,
        )
        for tool in tools
    ]
    registered_ids = {item.id for item in items}
    for tool_name in sorted(_discover_all_tool_names()):
        if tool_name not in registered_ids:
            items.append(
                ToolCatalogItem(
                    id=tool_name,
                    name=tool_name.replace("-", " ").title(),
                    domain="",
                    supports_local=_supports_local(tool_name),
                    supports_docker=_supports_docker(tool_name),
                    description="",
                )
            )
    return ToolCatalogResponse(items=items, total=len(items))


@tools_v1_router.get("/installed", response_model=InstalledToolsResponse)
def get_installed_tools(request: Request) -> InstalledToolsResponse:
    """Return the set of tool wrappers whose binary was found at process start.

    The probe runs once per process lifetime; the result is cached. The
    SPA uses this to gate UI affordances (e.g. hide tools from the scan
    picker when their binary isn't installed) before any project is
    selected. Auth-only; no project context required.
    """
    port = request.app.state.installed_tools
    return InstalledToolsResponse(installed=sorted(port.installed()))


@projects_tools_v1_router.get(
    "/{project_id}/tools/overrides",
    response_model=ToolOverrideListResponse,
)
async def get_tool_overrides(
    project_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> ToolOverrideListResponse:
    """Return project-level tool config overrides from the database."""
    service, _repo, _paths, _name = await asyncio.to_thread(
        _build_service, request, project_id
    )
    rows, total = await asyncio.to_thread(service.list, offset=offset, limit=limit)
    return ToolOverrideListResponse(
        items=[_to_response(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@projects_tools_v1_router.post(
    "/{project_id}/tools/overrides",
    status_code=201,
    response_model=ToolOverrideResponse,
)
async def create_tool_override(
    project_id: int,
    request: Request,
    body: ToolOverrideCreateRequest,
) -> ToolOverrideResponse:
    """Create a new project-scoped tool override."""
    service, _repo, _paths, _name = await asyncio.to_thread(
        _build_service, request, project_id
    )
    container_name = body.container.name if body.container else None
    container_tool_path = body.container.tool_path if body.container else None
    try:
        override = await asyncio.to_thread(
            service.create,
            tool_name=body.tool_name,
            args_mode=body.args_mode,
            type=body.type,
            location=body.location,
            path=body.path,
            container_name=container_name,
            container_tool_path=container_tool_path,
        )
    except ToolOverrideValidationError as exc:
        raise ApiValidationError(
            "request body failed validation",
            details={"fields": [asdict(f) for f in exc.fields]},
        ) from exc
    except ToolOverrideNameConflict as exc:
        raise Conflict(f"Tool override {body.tool_name!r} already exists") from exc

    return _to_response(override)


@projects_tools_v1_router.put(
    "/{project_id}/tools/overrides/{tool_name}",
    response_model=ToolOverrideResponse,
)
async def replace_tool_override(
    project_id: int,
    tool_name: str,
    request: Request,
    body: ToolOverrideReplaceRequest,
) -> ToolOverrideResponse:
    """Replace an existing project-scoped tool override."""
    if body.tool_name is not None and body.tool_name != tool_name:
        raise ApiValidationError(
            "request body failed validation",
            details={
                "fields": [
                    {
                        "field": "toolName",
                        "issue": "must match path parameter when present",
                    }
                ]
            },
        )
    service, _repo, _paths, _name = await asyncio.to_thread(
        _build_service, request, project_id
    )
    container_name = body.container.name if body.container else None
    container_tool_path = body.container.tool_path if body.container else None
    try:
        override = await asyncio.to_thread(
            service.replace,
            tool_name,
            args_mode=body.args_mode,
            type=body.type,
            location=body.location,
            path=body.path,
            container_name=container_name,
            container_tool_path=container_tool_path,
        )
    except ToolOverrideValidationError as exc:
        raise ApiValidationError(
            "request body failed validation",
            details={"fields": [asdict(f) for f in exc.fields]},
        ) from exc
    except ToolOverrideNotFound as exc:
        raise NotFound(f"Tool override {tool_name!r} not found") from exc

    return _to_response(override)


@projects_tools_v1_router.delete(
    "/{project_id}/tools/overrides/{tool_name}",
    status_code=204,
)
async def delete_tool_override(
    project_id: int,
    tool_name: str,
    request: Request,
) -> Response:
    """Delete a project-scoped tool override."""
    service, _repo, _paths, _name = await asyncio.to_thread(
        _build_service, request, project_id
    )
    existing = await asyncio.to_thread(service.get, tool_name)
    if existing is None:
        raise NotFound(f"Tool override {tool_name!r} not found")
    await asyncio.to_thread(service.delete, tool_name)
    return Response(status_code=204)

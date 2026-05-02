"""Tool catalog and tool override read endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Request, Response

from application.runtime.dependency_service import RuntimeDependencyService
from application.tools.registry import discover_tools, tool_registry
from core.config._atomic import atomic_write_text, locked_config
from core.config.schemas import CommandEntry
from core.project_paths import ProjectPaths
from web.api._errors import Conflict, NotFound
from web.api._errors import ValidationError as ApiValidationError
from web.api.schemas import (
    DockerContainerResponse,
    InstalledToolsResponse,
    RuntimeDependenciesResponse,
    RuntimeDependencyItem,
    ToolCatalogItem,
    ToolCatalogResponse,
    ToolOverrideCreateRequest,
    ToolOverrideItem,
    ToolOverrideResponse,
    ToolOverrideUpdateRequest,
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


@tools_v1_router.get("/catalog", response_model=ToolCatalogResponse)
def get_tools_catalog() -> ToolCatalogResponse:
    """Return metadata for all registered tool wrappers."""
    tools = tool_registry.get_all_tools()
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
    response_model=ToolOverrideResponse,
)
async def get_tool_overrides(
    project_id: int,
    request: Request,
) -> ToolOverrideResponse:
    """Return project-level tool config overrides from commands.json."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise NotFound(f"Project {project_id} not found")

    paths = ProjectPaths.from_registry_row(row)
    override_path = paths.commands_json

    if not override_path.exists():
        return ToolOverrideResponse(items=[], total=0)

    def _load() -> dict:
        with open(override_path) as f:
            return json.load(f)

    data: dict = await asyncio.to_thread(_load)

    items: list[ToolOverrideItem] = []
    for tool_id, entry_data in data.items():
        entry = CommandEntry(**entry_data)
        container = None
        if entry.container is not None:
            container = DockerContainerResponse(
                name=entry.container.name,
                tool_path=entry.container.tool_path,
            )
        items.append(
            ToolOverrideItem(
                tool_id=tool_id,
                type=entry.type,
                location=entry.location,
                path=entry.path or None,
                container=container,
            )
        )

    return ToolOverrideResponse(items=items, total=len(items))


def _entry_dict(
    *, type_: str, location: str, path: str, container: object | None
) -> dict:
    """Convert request fields into a JSON-serialisable commands.json entry."""
    container_dict: dict | None = None
    if container is not None:
        container_dict = {
            "name": container.name,  # type: ignore[attr-defined]
            "tool_path": container.tool_path,  # type: ignore[attr-defined]
        }
    return {
        "type": type_,
        "location": location,
        "path": path,
        "container": container_dict,
    }


def _validate_entry(entry: dict) -> CommandEntry:
    """Round-trip an entry dict through CommandEntry to validate constraints."""
    return CommandEntry(**entry)


def _to_response_item(tool_id: str, entry: CommandEntry) -> ToolOverrideItem:
    container = None
    if entry.container is not None:
        container = DockerContainerResponse(
            name=entry.container.name,
            tool_path=entry.container.tool_path,
        )
    return ToolOverrideItem(
        tool_id=tool_id,
        type=entry.type,
        location=entry.location,
        path=entry.path or None,
        container=container,
    )


def _load_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _refresh_registry(request: Request, project_name: str) -> None:
    """Refresh the in-memory tool registry after a write."""
    base_path: str = request.app.state.base_path
    discover_tools(base_path, project_name=project_name)


@projects_tools_v1_router.post(
    "/{project_id}/tools/overrides",
    status_code=201,
    response_model=ToolOverrideItem,
)
async def create_tool_override(
    project_id: int,
    request: Request,
    body: ToolOverrideCreateRequest,
) -> ToolOverrideItem:
    """Create a new project-scoped tool override in commands.json."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise NotFound(f"Project {project_id} not found")

    paths = ProjectPaths.from_registry_row(row)
    override_path = paths.commands_json
    paths.config_dir.mkdir(parents=True, exist_ok=True)

    entry_dict = _entry_dict(
        type_=body.type,
        location=body.location,
        path=body.path,
        container=body.container,
    )
    try:
        entry = _validate_entry(entry_dict)
    except Exception as exc:
        raise ApiValidationError(str(exc)) from exc

    with locked_config(override_path):
        data = _load_overrides(override_path)
        if body.tool_id in data:
            raise Conflict(f"Tool override '{body.tool_id}' already exists")
        data[body.tool_id] = entry_dict
        atomic_write_text(override_path, json.dumps(data, indent=2))

    _refresh_registry(request, row.name)
    return _to_response_item(body.tool_id, entry)


@projects_tools_v1_router.put(
    "/{project_id}/tools/overrides/{tool_id}",
    response_model=ToolOverrideItem,
)
async def replace_tool_override(
    project_id: int,
    tool_id: str,
    request: Request,
    body: ToolOverrideUpdateRequest,
) -> ToolOverrideItem:
    """Replace an existing project-scoped tool override."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise NotFound(f"Project {project_id} not found")

    paths = ProjectPaths.from_registry_row(row)
    override_path = paths.commands_json
    paths.config_dir.mkdir(parents=True, exist_ok=True)

    entry_dict = _entry_dict(
        type_=body.type,
        location=body.location,
        path=body.path,
        container=body.container,
    )
    try:
        entry = _validate_entry(entry_dict)
    except Exception as exc:
        raise ApiValidationError(str(exc)) from exc

    with locked_config(override_path):
        data = _load_overrides(override_path)
        if tool_id not in data:
            raise NotFound(f"Tool override '{tool_id}' not found")
        data[tool_id] = entry_dict
        atomic_write_text(override_path, json.dumps(data, indent=2))

    _refresh_registry(request, row.name)
    return _to_response_item(tool_id, entry)


@projects_tools_v1_router.delete(
    "/{project_id}/tools/overrides/{tool_id}",
    status_code=204,
)
async def delete_tool_override(
    project_id: int,
    tool_id: str,
    request: Request,
) -> Response:
    """Delete a project-scoped tool override."""
    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise NotFound(f"Project {project_id} not found")

    paths = ProjectPaths.from_registry_row(row)
    override_path = paths.commands_json

    with locked_config(override_path):
        data = _load_overrides(override_path)
        if tool_id not in data:
            raise NotFound(f"Tool override '{tool_id}' not found")
        del data[tool_id]
        atomic_write_text(override_path, json.dumps(data, indent=2))

    _refresh_registry(request, row.name)
    return Response(status_code=204)

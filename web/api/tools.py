"""Tool catalog and tool override read endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Request

from application.project.manager import ProjectManager
from application.runtime.dependency_service import RuntimeDependencyService
from application.tools.registry import tool_registry
from core.config.schemas import CommandEntry
from web.api._errors import NotFound
from web.api.schemas import (
    DockerContainerResponse,
    RuntimeDependenciesResponse,
    RuntimeDependencyItem,
    ToolCatalogItem,
    ToolCatalogResponse,
    ToolOverrideItem,
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


@projects_tools_v1_router.get(
    "/{project_name}/tools/overrides",
    response_model=ToolOverrideResponse,
)
async def get_tool_overrides(
    project_name: str,
    request: Request,
) -> ToolOverrideResponse:
    """Return project-level tool config overrides from commands.json."""
    base_path: str = request.app.state.base_path
    manager = ProjectManager(base_path)
    if manager.get_project_info(project_name) is None:
        raise NotFound(f"Project '{project_name}' not found")

    override_path = (
        Path(base_path) / "projects" / project_name / "config" / "commands.json"
    )

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

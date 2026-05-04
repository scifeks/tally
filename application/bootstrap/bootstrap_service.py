"""Startup orchestration shared by every driving adapter."""

from __future__ import annotations

from pathlib import Path

from application.ports.project_registry_repository import (
    ProjectRegistryRepositoryPort,
)
from application.project.registry_service import ProjectRegistryService
from application.scans.scans_service import ScansService
from application.setup.commands_setup import sync_commands_config
from application.tools.registry import ToolRegistry, discover_tools
from core.config._atomic import sweep_orphans


class BootstrapService:
    def __init__(
        self,
        registry_repo: ProjectRegistryRepositoryPort,
        project_registry: ProjectRegistryService,
        tool_registry: ToolRegistry,
        base_path: str,
    ) -> None:
        self._registry_repo = registry_repo
        self._project_registry = project_registry
        self._tool_registry = tool_registry
        self._base_path = base_path

    def run(self) -> None:
        sweep_orphans(Path(self._base_path))
        sync_commands_config(self._base_path)
        self._registry_repo.init_schema()
        self._project_registry.sync(self._base_path)
        ScansService.mark_stale_failed_for_all_projects(self._project_registry)
        discover_tools(self._tool_registry, self._base_path)

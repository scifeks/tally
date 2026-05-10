"""Startup orchestration shared by every driving adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from application.ports.project_registry_repository import (
    ProjectRegistryRepositoryPort,
)
from application.project.registry_service import ProjectRegistryService
from application.scans.scans_service import ScansService
from application.setup.commands_setup import sync_commands_config
from application.tools.registry import ToolRegistry, discover_tools
from core.config._atomic import sweep_orphans

if TYPE_CHECKING:
    from application.ports.run_repository import RunRepositoryPort


class BootstrapService:
    def __init__(
        self,
        registry_repo: ProjectRegistryRepositoryPort,
        project_registry: ProjectRegistryService,
        tool_registry: ToolRegistry,
        base_path: str,
        run_repo_factory: Callable[[Path], RunRepositoryPort] | None = None,
    ) -> None:
        self._registry_repo = registry_repo
        self._project_registry = project_registry
        self._tool_registry = tool_registry
        self._base_path = base_path
        self._run_repo_factory = run_repo_factory

    def run(self) -> None:
        sweep_orphans(Path(self._base_path))
        sync_commands_config(self._base_path)
        self._registry_repo.init_schema()
        self._project_registry.sync(self._base_path)
        if self._run_repo_factory is not None:
            ScansService.mark_stale_failed_for_all_projects(
                self._project_registry, self._run_repo_factory
            )
        discover_tools(self._tool_registry, self._base_path)

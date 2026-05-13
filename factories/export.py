"""Factory for export service construction."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.export.defectdojo.adapter import (
    DefectDojoExportAdapter,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository

if TYPE_CHECKING:
    from application.export.service import ExportService
    from application.project.registry_service import (
        ProjectRegistryService,
    )


class ExportNotConfigured(ValueError):
    """Raised when DefectDojo is not configured for the project."""


def _resolve_project(registry: ProjectRegistryService, project_id: int) -> tuple:
    from factories.persistence import ProjectNotFound

    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise ProjectNotFound(f"project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
    return row, paths


def create_export_service(
    registry: ProjectRegistryService,
    project_id: int,
    base_path: str | Path,
) -> ExportService:
    """Build an ExportService wired to the DefectDojo adapter."""
    from application.export.service import ExportService

    row, paths = _resolve_project(registry, project_id)

    config_manager = ConfigManager(str(base_path))

    global_config = config_manager.load_global_config()
    if global_config.defectdojo is None:
        raise ExportNotConfigured(
            "DefectDojo connection not configured. "
            "Add a 'defectdojo' section to global.json."
        )

    project_config = config_manager.load_project_config(row.name)
    if project_config is None or project_config.defectdojo is None:
        raise ExportNotConfigured(
            f"DefectDojo targeting not configured for "
            f"project {row.name!r}. Add a 'defectdojo' "
            "section to the project config."
        )

    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    finding_repo = FindingRepository(factory)
    export_adapter = DefectDojoExportAdapter(
        connection=global_config.defectdojo,
        project=project_config.defectdojo,
    )

    return ExportService(finding_repo, export_adapter)

"""Factory for export service construction."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import (
    RepositoryRepository,
)
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.url_findings import (
    UrlFindingRepository,
)

if TYPE_CHECKING:
    from application.export.selection import SyncSelector
    from application.export.service import ExportService
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from core.config.schemas.defectdojo_config import (
        DefectDojoGlobalConfig,
    )


class ExportNotConfigured(ValueError):
    """Raised when DefectDojo is not configured for the project."""


def build_export_service(
    dd_config: DefectDojoGlobalConfig,
    selector: SyncSelector,
    repo_names: dict[int, str],
    project_name: str,
    organization_name: str,
    engagement_name: str,
    run_id: int | None = None,
    url_finding_repo: UrlFindingRepositoryPort | None = None,
    repo_base_urls: dict[int, list[str]] | None = None,
) -> ExportService:
    """Build an ExportService with pre-resolved dependencies."""
    from application.export.service import ExportService
    from infrastructure.export.defectdojo.adapter import (
        DefectDojoExportAdapter,
    )

    export_adapter = DefectDojoExportAdapter(
        config=dd_config,
        repo_names=repo_names,
        project_name=project_name,
        organization_name=organization_name,
        engagement_name=engagement_name,
        url_finding_repo=url_finding_repo,
        repo_base_urls=repo_base_urls or {},
    )

    return ExportService(selector, export_adapter, run_id=run_id)


def create_export_service(
    registry: ProjectRegistryService,
    project_id: int,
    base_path: str | Path,
    run_id: int | None = None,
    engagement_name_override: str | None = None,
) -> ExportService:
    """Build an ExportService for a project in the registry."""
    from factories.persistence import ProjectNotFound

    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise ProjectNotFound(f"project {project_id} not found")
    return _create(
        base_path=base_path,
        project_name=row.name,
        paths=ProjectPaths.from_registry_row(row),
        run_id=run_id,
        engagement_name_override=engagement_name_override,
    )


def create_export_service_for_project(
    base_path: str | Path,
    project_name: str,
    run_id: int | None = None,
    engagement_name_override: str | None = None,
) -> ExportService:
    """Build an ExportService without requiring a ProjectRegistryService."""
    return _create(
        base_path=base_path,
        project_name=project_name,
        paths=ProjectPaths.from_canonical(base_path, project_name),
        run_id=run_id,
        engagement_name_override=engagement_name_override,
    )


def _create(
    *,
    base_path: str | Path,
    project_name: str,
    paths: ProjectPaths,
    run_id: int | None,
    engagement_name_override: str | None,
) -> ExportService:
    from application.export.selection import SyncSelector
    from application.ports.export import SyncRepo

    config_manager = ConfigManager(str(base_path))
    dd_config = config_manager.load_global_config().defectdojo
    if dd_config is None:
        raise ExportNotConfigured(
            "DefectDojo connection not configured. "
            "Add a 'defectdojo' section to global.json."
        )

    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    active_repos = RepositoryRepository(factory).list_active()

    project_config = config_manager.load_project_config(project_name)
    project_dd = project_config.defectdojo if project_config else None
    company_name = project_config.company_name if project_config else ""

    selector = SyncSelector(
        FindingRepository(factory),
        RunRepository(factory),
        [
            SyncRepo(r.id, tuple(s.name for s in r.services))
            for r in active_repos
            if r.id is not None
        ],
    )

    return build_export_service(
        dd_config=dd_config,
        selector=selector,
        repo_names={r.id: r.name for r in active_repos if r.id is not None},
        project_name=project_name,
        organization_name=company_name or project_name,
        engagement_name=(
            engagement_name_override
            or (project_dd.engagement_name if project_dd else None)
            or dd_config.engagement_name
        ),
        run_id=run_id,
        url_finding_repo=UrlFindingRepository(factory),
        repo_base_urls={
            r.id: (r.services[0].base_urls if r.services else [])
            for r in active_repos
            if r.id is not None
        },
    )

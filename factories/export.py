"""Factory for export service construction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.url_findings import (
    UrlFindingRepository,
)

if TYPE_CHECKING:
    from application.export.service import ExportService
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
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


def _resolve_project(registry: ProjectRegistryService, project_id: int) -> tuple:
    from factories.persistence import ProjectNotFound

    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise ProjectNotFound(f"project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
    return row, paths


def _build_run_mappings(
    factory: ConnectionFactory,
    repo_name_to_id: dict[str, int],
    run_id: int | None,
) -> tuple[dict[int, int], set[tuple[int | None, str]]]:
    where = "WHERE id = ?" if run_id is not None else ""
    params = (run_id,) if run_id is not None else ()

    with factory.connect() as conn:
        rows = conn.execute(
            f"SELECT id, repo_ids, tool_ids FROM scan_runs {where}",
            params,
        ).fetchall()

        run_ids = [r["id"] for r in rows]
        tools_by_run: dict[int, set[str]] = {}
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))
            run_tools_rows = conn.execute(
                f"SELECT DISTINCT run_id, tool FROM run_tools"
                f" WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchall()
            for rt in run_tools_rows:
                if rt["run_id"] not in tools_by_run:
                    tools_by_run[rt["run_id"]] = set()
                tools_by_run[rt["run_id"]].add(rt["tool"])

    run_to_repo_id: dict[int, int] = {}
    all_tool_runs: set[tuple[int | None, str]] = set()

    for r in rows:
        repo_names_json = json.loads(r["repo_ids"] or "[]")
        tool_names = json.loads(r["tool_ids"] or "[]")

        if len(repo_names_json) == 1:
            rid = repo_name_to_id.get(repo_names_json[0])
            if rid is not None:
                run_to_repo_id[r["id"]] = rid

        actual_tools = set(tool_names) | tools_by_run.get(r["id"], set())
        for repo_name in repo_names_json:
            rid = repo_name_to_id.get(repo_name)
            for tool in actual_tools:
                all_tool_runs.add((rid, tool))

    return run_to_repo_id, all_tool_runs


def build_export_service(
    dd_config: DefectDojoGlobalConfig,
    finding_repo: FindingRepositoryPort,
    repo_names: dict[int, str],
    project_name: str,
    engagement_type: str,
    run_id: int | None = None,
    run_to_repo_id: dict[int, int] | None = None,
    all_tool_runs: set[tuple[int | None, str]] | None = None,
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
        engagement_type=engagement_type,
        run_to_repo_id=run_to_repo_id or {},
        all_tool_runs=all_tool_runs or set(),
        url_finding_repo=url_finding_repo,
        repo_base_urls=repo_base_urls or {},
    )

    return ExportService(finding_repo, export_adapter, run_id=run_id)


def create_export_service(
    registry: ProjectRegistryService,
    project_id: int,
    base_path: str | Path,
    run_id: int | None = None,
    engagement_type_override: str | None = None,
) -> ExportService:
    """Build an ExportService wired to the DefectDojo adapter."""
    row, paths = _resolve_project(registry, project_id)

    config_manager = ConfigManager(str(base_path))

    global_config = config_manager.load_global_config()
    dd_config = global_config.defectdojo
    if dd_config is None:
        raise ExportNotConfigured(
            "DefectDojo connection not configured. "
            "Add a 'defectdojo' section to global.json."
        )

    from infrastructure.store.repositories.repositories import (
        RepositoryRepository,
    )

    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    repo_repo = RepositoryRepository(factory)
    repo_names = {r.id: r.name for r in repo_repo.list_active() if r.id is not None}
    repo_name_to_id = {name: rid for rid, name in repo_names.items()}

    run_to_repo_id, all_tool_runs = _build_run_mappings(
        factory, repo_name_to_id, run_id
    )

    project_config = config_manager.load_project_config(row.name)
    project_dd = project_config.defectdojo if project_config else None

    engagement_type = (
        engagement_type_override
        or (project_dd.engagement_type if project_dd else None)
        or dd_config.engagement_type
    )

    active_repos = repo_repo.list_active()
    repo_base_urls = {r.id: r.base_urls for r in active_repos if r.id is not None}

    finding_repo = FindingRepository(factory)
    url_finding_repo = UrlFindingRepository(factory)

    return build_export_service(
        dd_config=dd_config,
        finding_repo=finding_repo,
        repo_names=repo_names,
        project_name=row.name,
        engagement_type=engagement_type,
        run_id=run_id,
        run_to_repo_id=run_to_repo_id,
        all_tool_runs=all_tool_runs,
        url_finding_repo=url_finding_repo,
        repo_base_urls=repo_base_urls,
    )


def create_export_service_for_project(
    base_path: str | Path,
    project_name: str,
    run_id: int | None = None,
    engagement_type_override: str | None = None,
) -> ExportService:
    """Build an ExportService without requiring a ProjectRegistryService."""
    from infrastructure.store.repositories.repositories import (
        RepositoryRepository,
    )

    paths = ProjectPaths.from_canonical(base_path, project_name)
    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)

    config_manager = ConfigManager(str(base_path))
    global_config = config_manager.load_global_config()
    dd_config = global_config.defectdojo
    if dd_config is None:
        raise ExportNotConfigured(
            "DefectDojo connection not configured. "
            "Add a 'defectdojo' section to global.json."
        )

    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    repo_repo = RepositoryRepository(factory)
    active_repos = repo_repo.list_active()
    repo_names = {r.id: r.name for r in active_repos if r.id is not None}
    repo_name_to_id = {name: rid for rid, name in repo_names.items()}

    run_to_repo_id, all_tool_runs = _build_run_mappings(
        factory, repo_name_to_id, run_id
    )

    project_config = config_manager.load_project_config(project_name)
    project_dd = project_config.defectdojo if project_config else None

    engagement_type = (
        engagement_type_override
        or (project_dd.engagement_type if project_dd else None)
        or dd_config.engagement_type
    )

    repo_base_urls = {r.id: r.base_urls for r in active_repos if r.id is not None}

    finding_repo = FindingRepository(factory)
    url_finding_repo = UrlFindingRepository(factory)

    return build_export_service(
        dd_config=dd_config,
        finding_repo=finding_repo,
        repo_names=repo_names,
        project_name=project_name,
        engagement_type=engagement_type,
        run_id=run_id,
        run_to_repo_id=run_to_repo_id,
        all_tool_runs=all_tool_runs,
        url_finding_repo=url_finding_repo,
        repo_base_urls=repo_base_urls,
    )

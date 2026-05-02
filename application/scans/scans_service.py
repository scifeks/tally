"""Application service for the scan_runs persistence surface.

Owns per-request construction of the run repository so route modules
do not import infrastructure persistence directly. Also owns the
startup-time stale-scan sweep so the web composition root drops its
``ConnectionFactory`` / ``RunRepository`` / ``ProjectPaths`` imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Self

from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository

if TYPE_CHECKING:
    from application.ports.run_repository import RunRepositoryPort
    from application.project.registry_service import ProjectRegistryService


logger = logging.getLogger(__name__)


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class ScansService:
    """Scan_runs facade bound to a single project."""

    def __init__(self, run_repo: RunRepositoryPort) -> None:
        self._run_repo = run_repo

    @classmethod
    def for_project(
        cls,
        registry: ProjectRegistryService,
        project_id: int,
    ) -> Self:
        row = registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
            raise ProjectNotFound(f"project {project_id} not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        return cls(run_repo=RunRepository(factory))

    @property
    def run_repo(self) -> RunRepositoryPort:
        return self._run_repo

    @classmethod
    def mark_stale_failed_for_all_projects(
        cls, project_registry: ProjectRegistryService
    ) -> None:
        """Mark every ``running``/``cancelling`` scan_runs row as ``failed``.

        Tier-1 lock guarantees only one scan is live per process at a
        time, so any persisted-as-running row at boot belongs to a prior
        process that is no longer here. Iterates every active project's
        findings DB and sweeps once. Errors per-project are logged and
        skipped so one bad project does not block startup.
        """
        for project in project_registry.list_active():
            try:
                paths = ProjectPaths.from_registry_row(project)
                if not paths.findings_db.exists():
                    continue
                repo = RunRepository(ConnectionFactory(paths.findings_db))
                count = repo.mark_stale_runs_failed()
                if count:
                    logger.info(
                        "marked %d stale scan_runs as failed in project %s",
                        count,
                        project.name,
                    )
            except Exception:
                logger.exception(
                    "stale-scan cleanup failed for project %s", project.name
                )

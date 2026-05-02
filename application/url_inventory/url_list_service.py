"""Application service for the URL list web surface.

Owns per-request construction of the URL finding repo, the project
repo lookup, and the wrapping ``UrlInventoryService`` so route modules
do not import infrastructure persistence directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from application.url_inventory.service import UrlInventoryService
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.url_findings import UrlFindingRepository

if TYPE_CHECKING:
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from application.project.registry_service import ProjectRegistryService


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class UrlListService:
    """URL list facade bound to a single project."""

    def __init__(
        self,
        url_repo: UrlFindingRepositoryPort,
        project_repo: ProjectRepoRepositoryPort,
        inventory: UrlInventoryService,
        *,
        findings_db_exists: bool,
    ) -> None:
        self._url_repo = url_repo
        self._project_repo = project_repo
        self._inventory = inventory
        self._findings_db_exists = findings_db_exists

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
        # Capture before init_schema(): init creates the file, and the
        # defensive count helpers need to know whether the project has
        # any persisted url_findings yet.
        findings_db_exists = paths.findings_db.exists()
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)
        project_repo = RepositoryRepository(factory)
        inventory = UrlInventoryService(url_repo)
        return cls(
            url_repo=url_repo,
            project_repo=project_repo,
            inventory=inventory,
            findings_db_exists=findings_db_exists,
        )

    @property
    def url_repo(self) -> UrlFindingRepositoryPort:
        return self._url_repo

    @property
    def inventory(self) -> UrlInventoryService:
        return self._inventory

    def repo_name_lookup(self) -> dict[int, str]:
        """Build ``{repo_id: repo_name}`` for the project's active repos.

        Returns ``{}`` when the findings DB has not been created yet
        or when the underlying read raises. The defensive shape is
        load-bearing for the URL list routes.
        """
        if not self._findings_db_exists:
            return {}
        try:
            return {
                r.id: r.name
                for r in self._project_repo.list_active()
                if r.name and isinstance(r.id, int)
            }
        except Exception:
            return {}

    def count_active_url_findings(self) -> int:
        """Count url_findings rows whose owning repo is not soft-deleted.

        Returns 0 when the findings DB has not been created yet or
        when the underlying read raises.
        """
        if not self._findings_db_exists:
            return 0
        try:
            return self._url_repo.count_active()
        except Exception:
            return 0

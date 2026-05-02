"""Application service for findings persistence + analyst access.

Owns per-request construction of the finding, history, and project-repo
repos so route modules do not import infrastructure persistence directly.
Composes a `FindingAnalystService` and exposes the history repo + a
`repo_name_lookup()` helper that the routes need.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from application.findings.analyst_service import FindingAnalystService
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.finding_history import (
    FindingHistoryRepository,
)
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import RepositoryRepository

if TYPE_CHECKING:
    from fastapi import Request

    from application.ports.finding_history_repository import (
        FindingHistoryRepositoryPort,
    )
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class FindingsService:
    """Findings-feature facade bound to a single project."""

    def __init__(
        self,
        finding_repo: FindingRepositoryPort,
        history_repo: FindingHistoryRepositoryPort,
        project_repo: ProjectRepoRepositoryPort,
        analyst: FindingAnalystService,
        *,
        findings_db_exists: bool,
    ) -> None:
        self._finding_repo = finding_repo
        self._history_repo = history_repo
        self._project_repo = project_repo
        self._analyst = analyst
        self._findings_db_exists = findings_db_exists

    @classmethod
    def from_request(cls, request: Request, project_id: int) -> Self:
        registry = request.app.state.project_registry
        row = registry.resolve_by_id(project_id)
        if row is None or row.get("archived_at"):
            raise ProjectNotFound(f"project {project_id} not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        # Capture before init_schema(): init creates the file, and
        # repo_name_lookup needs to know whether the project has any
        # persisted findings yet.
        findings_db_exists = paths.findings_db.exists()
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        finding_repo = FindingRepository(factory)
        history_repo = FindingHistoryRepository(factory)
        project_repo = RepositoryRepository(factory)
        analyst = FindingAnalystService(finding_repo)
        return cls(
            finding_repo=finding_repo,
            history_repo=history_repo,
            project_repo=project_repo,
            analyst=analyst,
            findings_db_exists=findings_db_exists,
        )

    @property
    def analyst(self) -> FindingAnalystService:
        return self._analyst

    @property
    def finding_repo(self) -> FindingRepositoryPort:
        return self._finding_repo

    @property
    def history_repo(self) -> FindingHistoryRepositoryPort:
        return self._history_repo

    def repo_name_lookup(self) -> dict[int, str]:
        """Build ``{repo_id: repo_name}`` for the project's active repos.

        Returns ``{}`` when the findings DB has not been created yet
        (a brand-new project hits the list route before any scan) or
        when the underlying read raises. The defensive shape is
        load-bearing for the list route.
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

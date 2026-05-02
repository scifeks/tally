"""Application service for findings persistence + analyst access.

Owns per-request construction of repos so routes avoid direct imports of
infrastructure persistence. Composes FindingAnalystService and exposes
history repo + repo_name_lookup helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from application.findings.analyst_service import FindingAnalystService
from application.locking import LockQueryService
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.finding_history import (
    FindingHistoryRepository,
)
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import RepositoryRepository

if TYPE_CHECKING:
    from application.ports.finding_history_repository import (
        FindingHistoryRepositoryPort,
    )
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.project.registry_service import ProjectRegistryService


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
        lock_query: LockQueryService,
        *,
        findings_db_exists: bool,
    ) -> None:
        self._finding_repo = finding_repo
        self._history_repo = history_repo
        self._project_repo = project_repo
        self._analyst = analyst
        self._lock_query = lock_query
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
            lock_query=LockQueryService(),
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
        """Return {repo_id: repo_name} for active repos.

        Returns empty dict when the findings DB has not been created yet
        or when the underlying read raises.
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

    def lock_state_for(self, finding_id: int) -> tuple[bool, str | None]:
        """Return (is_locked, lock_holder) for a single finding."""
        return (
            self._lock_query.is_finding_locked(finding_id),
            self._lock_query.finding_lock_holder(finding_id),
        )

    def count_findings(self) -> int:
        """Total count of rows in the findings table.

        Returns 0 when the findings DB has not been created yet or
        when the underlying read raises.
        """
        if not self._findings_db_exists:
            return 0
        try:
            return self._finding_repo.count_findings()
        except Exception:
            return 0

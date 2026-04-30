"""Application-layer facade for project-scoped repository queries.

API and CLI adapters call this service rather than reaching across into
``ProjectManager`` / ``ConfigManager`` / ``RepositoryRepository`` directly.
The service composes those collaborators internally so the adapter only
depends on this single application boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.config import ConfigManager, Repository

if TYPE_CHECKING:
    from fastapi import Request

    from application.project.registry_service import ProjectRegistryService


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


@dataclass(frozen=True)
class RepoLookupResult:
    """Outcome of resolving a list of caller-supplied repo ids.

    ``found`` preserves caller order; ``missing`` lists ids in the order
    they were supplied; ``available`` is a sorted snapshot of every active
    repo id in the project.
    """

    found: dict[int, Repository] = field(default_factory=dict)
    missing: list[int] = field(default_factory=list)
    available: list[int] = field(default_factory=list)


class ProjectRepositoriesService:
    """Read-side queries for the active repositories of a project."""

    def __init__(
        self,
        registry: ProjectRegistryService,
        config_manager: ConfigManager,
    ) -> None:
        self._registry = registry
        self._config_manager = config_manager

    @classmethod
    def from_request(cls, request: Request) -> ProjectRepositoriesService:
        """Build a service from the request-level app state."""
        registry: ProjectRegistryService = request.app.state.project_registry
        base_path: str = request.app.state.base_path
        return cls(registry, ConfigManager(base_path, registry=registry))

    def list_active(self, project_id: int) -> list[Repository]:
        """Return every active repository in the project, DB-id populated.

        Soft-deleted repos and repos with no DB row are excluded; callers
        get back only entries with an integer ``id``.
        """
        project_name = self._project_name(project_id)
        repos = self._config_manager.load_repositories(project_name)
        return [r for r in repos if isinstance(r.id, int)]

    def find_by_ids(self, project_id: int, repo_ids: Sequence[int]) -> RepoLookupResult:
        """Resolve caller-supplied ids against the project's active repos."""
        by_id: dict[int, Repository] = {}
        for repo in self.list_active(project_id):
            if isinstance(repo.id, int):
                by_id[repo.id] = repo
        found = {rid: by_id[rid] for rid in repo_ids if rid in by_id}
        missing = [rid for rid in repo_ids if rid not in by_id]
        return RepoLookupResult(
            found=found,
            missing=missing,
            available=sorted(by_id.keys()),
        )

    def _project_name(self, project_id: int) -> str:
        row = self._registry.resolve_by_id(project_id)
        if row is None or row.get("archived_at"):
            raise ProjectNotFound(f"Project {project_id} not found")
        return row["name"]

"""Application-layer facade for project-scoped repository CRUD.

Adapters call this instead of importing ProjectManager, ConfigManager, or
RepositoryRepository directly. The SQLite repositories table is the sole
source of truth; this service is the single write surface.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.config import ConfigManager, Repository
from core.config.schemas.repository import RepoAuth
from core.project_paths import ProjectPaths

if TYPE_CHECKING:
    from application.ports.project_repo_repository import ProjectRepoRepositoryPort
    from application.project.registry_service import ProjectRegistryService


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class RepositoryNotFound(LookupError):
    """Raised when a repo_id has no active row in the project's DB."""


class DuplicateRepositoryName(ValueError):
    """Raised when create / update collides with an existing repo's name."""


class RepositoryPathNotFound(ValueError):
    """Raised when a repository path does not exist on the filesystem."""


@dataclass(frozen=True)
class RepoLookupResult:
    """Outcome of resolving a list of caller-supplied repo ids."""

    found: dict[int, Repository] = field(default_factory=dict)
    missing: list[int] = field(default_factory=list)
    available: list[int] = field(default_factory=list)


_FORM_ONLY_FIELDS = frozenset(
    {
        "login_url",
        "username_field",
        "password_field",
        "extra_fields",
        "credentials_env",
        "username",
        "password",
    }
)


def _clean_auth_type_switch(
    merged: dict[str, Any],
    old: dict[str, Any],
) -> dict[str, Any]:
    """Clear fields that belong to the previous auth type."""
    new_type = merged.get("auth_type", "form")
    old_type = old.get("auth_type", "form")
    if new_type == old_type:
        return merged
    if new_type == "header":
        for k in _FORM_ONLY_FIELDS:
            merged[k] = type(merged.get(k, ""))()
    elif new_type == "form":
        merged["auth_headers"] = []
    return merged


def _is_auth_cleared(
    merged: dict[str, Any],
    patch: dict[str, Any],
) -> bool:
    """Detect when the patch empties all credentials for the current auth type."""
    auth_type = merged.get("auth_type", "form")
    if auth_type == "header" and "auth_headers" in patch:
        return not merged.get("auth_headers")
    if auth_type == "form" and "login_url" in patch:
        return not merged.get("login_url")
    return False


class ProjectRepositoriesService:
    """CRUD facade for the active repositories of a project."""

    def __init__(
        self,
        registry: ProjectRegistryService,
        config_manager: ConfigManager,
        repo_factory: Callable[[int], ProjectRepoRepositoryPort] | None = None,
    ) -> None:
        self._registry = registry
        self._config_manager = config_manager
        self._repo_factory = repo_factory

    @classmethod
    def build(
        cls,
        registry: ProjectRegistryService,
        base_path: str,
    ) -> ProjectRepositoriesService:
        """Build a service from the registry and the Tally base path."""
        return cls(registry, ConfigManager(base_path, registry=registry))

    def list_active(self, project_id: int) -> list[Repository]:
        """Return every active repository in the project."""
        repo_repo = self._repo_repo(project_id)
        return repo_repo.list_active()

    def get(self, project_id: int, repo_id: int) -> Repository:
        """Return a single active repo, or raise ``RepositoryNotFound``."""
        repo_repo = self._repo_repo(project_id)
        repo = repo_repo.get_active_by_id(repo_id)
        if repo is None:
            raise RepositoryNotFound(f"Repository {repo_id} not found")
        return repo

    def find_by_ids(self, project_id: int, repo_ids: Sequence[int]) -> RepoLookupResult:
        """Resolve caller-supplied ids against the project's active repos."""
        active = self.list_active(project_id)
        by_id: dict[int, Repository] = {
            r.id: r for r in active if isinstance(r.id, int)
        }
        found = {rid: by_id[rid] for rid in repo_ids if rid in by_id}
        missing = [rid for rid in repo_ids if rid not in by_id]
        return RepoLookupResult(
            found=found,
            missing=missing,
            available=sorted(by_id.keys()),
        )

    def create(self, project_id: int, repo: Repository) -> Repository:
        """Insert *repo*; return the persisted Repository with ``id`` set."""
        repo_repo = self._repo_repo(project_id)
        if repo_repo.get_by_name(repo.name) is not None:
            raise DuplicateRepositoryName(
                f"Repository '{repo.name}' already exists in project"
            )
        if repo.path and not Path(repo.path).exists():
            raise RepositoryPathNotFound(f"Repository path does not exist: {repo.path}")
        new_id = repo_repo.insert(repo)
        persisted = repo_repo.get_by_id(new_id)
        if persisted is None:
            raise RepositoryNotFound(f"Repository {new_id} not found after insert")
        return persisted

    def update(
        self, project_id: int, repo_id: int, patch: dict[str, Any]
    ) -> Repository:
        """Merge *patch* into the existing repo; persist; return the result."""
        repo_repo = self._repo_repo(project_id)
        existing = repo_repo.get_active_by_id(repo_id)
        if existing is None:
            raise RepositoryNotFound(f"Repository {repo_id} not found")

        merged = existing.model_dump()
        merged.update(patch)
        # `id` and `url_seed_file` are excluded from model_dump (exclude=True);
        # carry them across so the rebuilt Repository keeps its identity.
        updated = Repository(**merged).model_copy(
            update={
                "id": existing.id,
                "url_seed_file": existing.url_seed_file,
            }
        )

        if updated.path and not Path(updated.path).exists():
            raise RepositoryPathNotFound(
                f"Repository path does not exist: {updated.path}"
            )

        if updated.name != existing.name:
            collision = repo_repo.get_by_name(updated.name)
            if collision is not None and collision.id != repo_id:
                raise DuplicateRepositoryName(
                    f"Repository '{updated.name}' already exists in project"
                )

        repo_repo.update(repo_id, updated)
        return updated

    def update_auth(
        self, project_id: int, repo_id: int, auth_patch: dict[str, Any]
    ) -> Repository:
        """Merge *auth_patch* into the repo's auth block; persist; return."""
        repo_repo = self._repo_repo(project_id)
        existing = repo_repo.get_active_by_id(repo_id)
        if existing is None:
            raise RepositoryNotFound(f"Repository {repo_id} not found")
        existing_auth = existing.auth.model_dump() if existing.auth is not None else {}
        merged_auth = {**existing_auth, **auth_patch}
        if existing_auth:
            merged_auth = _clean_auth_type_switch(merged_auth, existing_auth)
        if _is_auth_cleared(merged_auth, auth_patch):
            new_auth = None
        else:
            new_auth = RepoAuth(**merged_auth)
        updated = existing.model_copy(update={"auth": new_auth})
        repo_repo.update(repo_id, updated)
        return updated

    def delete(self, project_id: int, repo_id: int) -> None:
        """Soft-delete the repo and clear its ``url_seed_file`` pointer.

        Raises ``RepositoryNotFound`` if the row is missing or already
        soft-deleted; the API surface relies on this to return 404 on
        the second delete of the same id.
        """
        repo_repo = self._repo_repo(project_id)
        if repo_repo.get_active_by_id(repo_id) is None:
            raise RepositoryNotFound(f"Repository {repo_id} not found")
        repo_repo.set_url_seed_file(repo_id, None)
        repo_repo.soft_delete(repo_id)

    def record_seed_file(self, project_id: int, repo_id: int, abs_path: str) -> None:
        """Persist the most-recent seed-file path for the repo."""
        repo_repo = self._repo_repo(project_id)
        if repo_repo.get_active_by_id(repo_id) is None:
            raise RepositoryNotFound(f"Repository {repo_id} not found")
        repo_repo.set_url_seed_file(repo_id, abs_path)

    # Internals
    def _project_name(self, project_id: int) -> str:
        row = self._registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
            raise ProjectNotFound(f"Project {project_id} not found")
        return row.name

    def _project_paths(self, project_id: int) -> ProjectPaths:
        row = self._registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
            raise ProjectNotFound(f"Project {project_id} not found")
        return ProjectPaths.from_registry_row(row)

    def _repo_repo(self, project_id: int) -> ProjectRepoRepositoryPort:
        if self._repo_factory is not None:
            return self._repo_factory(project_id)
        from factories.persistence import create_repo_repo

        paths = self._project_paths(project_id)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        return create_repo_repo(paths.findings_db)

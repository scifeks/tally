"""Project registry service — application-layer facade over the registry repo."""

from __future__ import annotations

from core.project_paths import ProjectPaths
from infrastructure.store.project_registry import ProjectRegistryRepository


class ProjectRegistryService:
    """Application-layer facade over ProjectRegistryRepository."""

    def __init__(self, repository: ProjectRegistryRepository) -> None:
        self._repo = repository

    def sync(self, base_path: str) -> None:
        self._repo.sync_from_filesystem(base_path)

    def ping(self) -> None:
        """Verify the registry DB is reachable. Raises on failure."""
        self._repo.ping()

    def list_active(self) -> list[dict]:
        return self._repo.list_active()

    def resolve_by_id(self, project_id: int) -> dict | None:
        return self._repo.get_by_id(project_id)

    def resolve_by_name(self, name: str) -> dict | None:
        return self._repo.get_by_name(name)

    def register(self, name: str, base_path: str) -> int:
        """Insert, un-archive, or no-op. Returns the integer id (idempotent)."""
        canonical = str(ProjectPaths.from_canonical(base_path, name).root.resolve())
        existing = self._repo.get_by_name(name)
        if existing is None:
            return self._repo.insert(name, canonical)
        if existing.get("archived_at") is not None:
            self._repo.unarchive(name, canonical)
            return int(existing["id"])
        return int(existing["id"])

    def deregister(self, name: str) -> None:
        self._repo.archive(name)

    def rename(self, old: str, new: str, base_path: str) -> None:
        new_path = str(ProjectPaths.from_canonical(base_path, new).root.resolve())
        self._repo.rename(old, new, new_path)

"""Project resolution for CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.project.registry_service import ProjectRegistryService
    from domain.projects.entry import ProjectRow


class ProjectResolutionError(LookupError):
    """Raised when a project cannot be resolved."""


def resolve_project(
    registry: ProjectRegistryService, name: str
) -> tuple[int, ProjectRow]:
    """Resolve a project by name, raising ProjectResolutionError on miss."""
    row = registry.resolve_by_name(name)
    if row is None:
        raise ProjectResolutionError(f"project not found: {name}")
    if row.archived_at is not None:
        raise ProjectResolutionError(f"project '{name}' is archived and cannot be used")
    return (row.id, row)

"""Project management for tally Security Auditing REPL."""

import datetime
import shutil
from pathlib import Path

from application.project.registry_service import ProjectRegistryService
from core.config import ConfigManager, ProjectConfig
from core.project_paths import ProjectPaths


class ProjectManager:
    """Manages tally projects: creation, listing, switching, and repositories."""

    def __init__(
        self,
        base_path: str = ".",
        registry: ProjectRegistryService | None = None,
    ):
        self.base_path = Path(base_path)
        self.projects_dir = ProjectPaths.projects_dir(self.base_path)
        if registry is None:
            registry = _build_default_registry(base_path)
        self.registry = registry
        self.config = ConfigManager(base_path, registry=registry)

    # Public API

    def list_projects(self) -> list[str]:
        """Return sorted list of active project names from the registry."""
        return [row.name for row in self.registry.list_active()]

    def switch_project(self, project_name: str) -> None:
        """Validate that project_name exists in the registry and is not archived.

        Raises ValueError if the project is unknown. Callers update their own
        in-memory active-project state after this returns successfully.
        """
        row = self.registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            raise ValueError(f"Project '{project_name}' does not exist.")
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def get_project_info(self, project_name: str) -> ProjectConfig | None:
        """Load and return ProjectConfig for project_name."""
        return self.config.load_project_config(project_name)

    def delete_project(self, project_name: str) -> None:
        """Delete a project and all its data from disk + registry."""
        row = self.registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            raise ValueError(f"Project '{project_name}' not found.")
        project_dir = Path(row.path)
        if project_dir.exists():
            shutil.rmtree(project_dir)
        self.registry.deregister(project_name)

    def delete_repository(self, project_name: str, repo_name: str) -> None:
        """Soft-delete a repository in *project_name* by name."""
        from application.project.repositories_service import (
            ProjectRepositoriesService,
        )

        row = self.registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            raise ValueError(f"Project '{project_name}' does not exist.")
        service = ProjectRepositoriesService(self.registry, self.config)
        project_id = row.id
        target = next(
            (r for r in service.list_active(project_id) if r.name == repo_name),
            None,
        )
        if target is None or target.id is None:
            raise ValueError(f"Repository '{repo_name}' not found in '{project_name}'.")
        service.delete(project_id, target.id)

    # Filesystem helpers

    def create_project_dirs(self, name: str) -> None:
        """Create the standard subdirectory tree for a new project."""
        paths = ProjectPaths(self.projects_dir / name)
        dirs = [
            paths.endpoints_config_dir,
            paths.chroma_db,
            paths.sqlite_dir,
            paths.tool_output_dir("semgrep"),
            paths.tool_output_dir("osv-scanner"),
            paths.tool_output_dir("pip-audit"),
            paths.tool_output_dir("npm-audit"),
            paths.tool_output_dir("composer-audit"),
            paths.tool_output_dir("gitleaks"),
            paths.tool_output_dir("zap"),
            paths.sessions_dir,
            paths.endpoints_original_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def save_project(
        self,
        name: str,
        company_name: str = "",
        department_name: str = "",
        abbreviation: str = "",
    ) -> None:
        """Persist project-level fields to project.json and register the project.

        Per-repo data is owned by the SQLite ``repositories`` table; callers
        that need to persist repos do so via ``ProjectRepositoriesService``.
        """
        project_cfg = ProjectConfig(
            project_name=name,
            created=datetime.datetime.now().isoformat(),
            company_name=company_name,
            department_name=department_name,
            abbreviation=abbreviation,
        )
        self.config.save_project_config(name, project_cfg)
        self.registry.register(name, str(self.base_path))


def _build_default_registry(base_path: str) -> ProjectRegistryService:
    """Lazy-build a registry rooted at base_path/tally.db (sync from disk)."""
    from infrastructure.store.project_registry import ProjectRegistryRepository

    repo = ProjectRegistryRepository(Path(base_path) / "tally.db")
    repo.init_schema()
    svc = ProjectRegistryService(repo)
    svc.sync(base_path)
    return svc

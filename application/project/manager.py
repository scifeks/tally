"""Project management for tally Security Auditing REPL."""

import datetime
import shutil
from pathlib import Path

from core.config import ConfigManager, ProjectConfig, Repository


class ProjectManager:
    """Manages tally projects: creation, listing, switching, and repositories."""

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.projects_dir = self.base_path / "projects"
        self.active_file = self.projects_dir / ".active"
        self.config = ConfigManager(base_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_projects(self) -> list[str]:
        """Return sorted list of project names found in projects/."""
        if not self.projects_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.projects_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and (d / "config" / "project.json").exists()
        )

    def get_active_project(self) -> str | None:
        """Return the currently active project name, or None."""
        if not self.active_file.exists():
            return None
        name = self.active_file.read_text().strip()
        return name if name else None

    def switch_project(self, project_name: str) -> None:
        """Set project_name as the active project.

        Raises:
            ValueError: if the project does not exist.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.active_file.write_text(project_name)

    def get_project_info(self, project_name: str) -> ProjectConfig | None:
        """Load and return ProjectConfig for project_name."""
        return self.config.load_project_config(project_name)

    def delete_project(self, project_name: str) -> None:
        """Delete a project and all its data from disk.

        Raises:
            ValueError: If the project does not exist.
        """
        project_dir = self.projects_dir / project_name
        if not project_dir.exists():
            raise ValueError(f"Project '{project_name}' not found.")
        shutil.rmtree(project_dir)

        # Clear .active file if it points to the deleted project
        active_file = self.projects_dir / ".active"
        if active_file.exists():
            try:
                current = active_file.read_text().strip()
                if current == project_name:
                    active_file.unlink()
            except OSError:
                pass

    def delete_repository(self, project_name: str, repo_name: str) -> None:
        """Remove a repository from project_name by name.

        Raises:
            ValueError: if the project or repository does not exist.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        repos = self.config.load_repositories(project_name)
        new_repos = [r for r in repos if r.name != repo_name]
        if len(new_repos) == len(repos):
            raise ValueError(f"Repository '{repo_name}' not found in '{project_name}'.")
        self.config.save_repositories(project_name, new_repos)

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------

    def create_project_dirs(self, name: str) -> None:
        project_root = self.projects_dir / name
        dirs = [
            project_root / "config" / "endpoints",
            project_root / "chroma_db",
            project_root / "sqlite",
            project_root / "tool_outputs" / "semgrep",
            project_root / "tool_outputs" / "osv-scanner",
            project_root / "tool_outputs" / "pip-audit",
            project_root / "tool_outputs" / "npm-audit",
            project_root / "tool_outputs" / "composer-audit",
            project_root / "tool_outputs" / "gitleaks",
            project_root / "tool_outputs" / "zap",
            project_root / "sessions",
            project_root / "endpoints" / "original",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def save_project(
        self,
        name: str,
        repositories: list[Repository],
        company_name: str = "",
        department_name: str = "",
        abbreviation: str = "",
    ) -> None:
        project_cfg = ProjectConfig(
            project_name=name,
            created=datetime.datetime.now().isoformat(),
            repositories=repositories,
            company_name=company_name,
            department_name=department_name,
            abbreviation=abbreviation,
        )
        self.config.save_project_config(name, project_cfg)

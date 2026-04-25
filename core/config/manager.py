"""Configuration management for global and project settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.project_paths import ProjectPaths

from .schemas import (
    CommandEntry,
    EndpointConfig,
    GlobalConfig,
    ProjectConfig,
    Repository,
)

if TYPE_CHECKING:
    from application.project.registry_service import ProjectRegistryService


class ConfigManager:
    """Manages global and project-specific configurations."""

    def __init__(
        self,
        base_path: str = ".",
        registry: ProjectRegistryService | None = None,
    ):
        self.base_path = Path(base_path)
        self.global_config_path = self.base_path / "config" / "global.json"
        self.projects_dir = ProjectPaths.projects_dir(self.base_path)
        self._registry = registry

        self.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.global_config = self.load_global_config()

    def _project_paths(self, project_name: str) -> ProjectPaths:
        """Resolve a project's on-disk root via the registry, with fallback."""
        if self._registry is not None:
            row = self._registry.resolve_by_name(project_name)
            if row is not None and not row.get("archived_at"):
                return ProjectPaths.from_registry_row(row)
        return ProjectPaths(self.projects_dir / project_name)

    def load_global_config(self) -> GlobalConfig:
        """Load global configuration from disk."""
        if not self.global_config_path.exists():
            raise FileNotFoundError(
                f"Global config not found at {self.global_config_path}. "
                "Create it with the required fields: ollama.model, "
                "ollama_embedding.model."
            )
        with open(self.global_config_path) as f:
            data = json.load(f)
        try:
            return GlobalConfig(**data)
        except Exception as exc:
            raise ValueError(
                f"Invalid global config at {self.global_config_path}: {exc}"
            ) from exc

    def save_global_config(self, config: GlobalConfig) -> None:
        """Save global configuration to disk."""
        with open(self.global_config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

    def load_project_config(self, project_name: str) -> ProjectConfig | None:
        """Load project configuration."""
        config_path = self._project_paths(project_name).config_json
        if not config_path.exists():
            return None
        with open(config_path) as f:
            data = json.load(f)
            return ProjectConfig(**data)

    def save_project_config(self, project_name: str, config: ProjectConfig) -> None:
        """Save project configuration. Implicitly registers the project."""
        config_path = self._project_paths(project_name).config_json
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)
        if self._registry is not None:
            self._registry.register(project_name, str(self.base_path))

    def load_repositories(self, project_name: str) -> list[Repository]:
        """Load repositories from project.json for a project."""
        config = self.load_project_config(project_name)
        if config is None:
            return []
        return config.repositories

    def save_repositories(
        self, project_name: str, repositories: list[Repository]
    ) -> None:
        """Save repositories into project.json for a project."""
        config = self.load_project_config(project_name)
        if config is None:
            raise ValueError(f"Project '{project_name}' not found.")
        config.repositories = repositories
        self.save_project_config(project_name, config)

    def load_endpoint_config(
        self, project_name: str, repo_name: str
    ) -> EndpointConfig | None:
        """Load endpoint configuration for a repository."""
        config_path = self._project_paths(project_name).endpoint_config_json(repo_name)
        if not config_path.exists():
            return None
        with open(config_path) as f:
            data = json.load(f)
            return EndpointConfig(**data)

    def load_commands_config(self) -> dict[str, CommandEntry] | None:
        """Load commands.json from the app config directory."""
        config_path = self.base_path / "config" / "commands.json"
        if not config_path.exists():
            return None
        with open(config_path) as f:
            data = json.load(f)
        return {name: CommandEntry(**entry) for name, entry in data.items()}

    def save_commands_config(self, config: dict[str, CommandEntry]) -> None:
        """Save commands.json to the app config directory."""
        config_path = self.base_path / "config" / "commands.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: entry.model_dump() for name, entry in config.items()}
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

    def save_endpoint_config(self, project_name: str, config: EndpointConfig) -> None:
        """Save endpoint configuration for a repository."""
        config_path = self._project_paths(project_name).endpoint_config_json(
            config.repo_name
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

"""Configuration management for global and project settings."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from core.project_paths import ProjectPaths

from ._atomic import atomic_write_text, locked_config
from .schemas import (
    CommandEntry,
    EndpointConfig,
    GlobalConfig,
    ProjectConfig,
)

if TYPE_CHECKING:
    from application.project.registry_service import ProjectRegistryService


class ConfigManager:
    """Manages global and project-specific configurations.

    Every save method writes atomically (temp file + os.replace). Callers
    that perform load → modify → save sequences must wrap the sequence in
    one of the ``locked_*`` context managers so the entire cycle is
    exclusive against other processes/tasks.
    """

    def __init__(
        self,
        base_path: str = ".",
        registry: ProjectRegistryService | None = None,
    ):
        self.base_path = Path(base_path)
        self.global_config_path = self.base_path / "config" / "global.json"
        self.commands_config_path = self.base_path / "config" / "commands.json"
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

    def project_config_path(self, project_name: str) -> Path:
        """Return the project.json path. Useful for external locking."""
        return self._project_paths(project_name).config_json

    @contextmanager
    def locked_global_config(self) -> Iterator[Path]:
        """Hold an exclusive lock around the global config file."""
        with locked_config(self.global_config_path) as path:
            yield path

    @contextmanager
    def locked_commands_config(self) -> Iterator[Path]:
        """Hold an exclusive lock around the commands.json file."""
        with locked_config(self.commands_config_path) as path:
            yield path

    @contextmanager
    def locked_project_config(self, project_name: str) -> Iterator[Path]:
        """Hold an exclusive lock around a project's project.json."""
        with locked_config(self.project_config_path(project_name)) as path:
            yield path

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
        """Save global configuration atomically."""
        atomic_write_text(
            self.global_config_path,
            json.dumps(config.model_dump(), indent=2),
        )

    def load_project_config(self, project_name: str) -> ProjectConfig | None:
        """Load project configuration."""
        config_path = self.project_config_path(project_name)
        if not config_path.exists():
            return None
        with open(config_path) as f:
            data = json.load(f)
            return ProjectConfig(**data)

    def save_project_config(self, project_name: str, config: ProjectConfig) -> None:
        """Save project configuration atomically. Implicitly registers project.

        Does not acquire a lock. Callers that load → modify → save must wrap
        the cycle in ``locked_project_config(project_name)``.
        """
        config_path = self.project_config_path(project_name)
        atomic_write_text(config_path, json.dumps(config.model_dump(), indent=2))
        if self._registry is not None:
            self._registry.register(project_name, str(self.base_path))

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
        if not self.commands_config_path.exists():
            return None
        with open(self.commands_config_path) as f:
            data = json.load(f)
        return {name: CommandEntry(**entry) for name, entry in data.items()}

    def save_commands_config(self, config: dict[str, CommandEntry]) -> None:
        """Save commands.json atomically.

        Does not acquire a lock. Callers that load → modify → save must wrap
        the cycle in ``locked_commands_config()``.
        """
        data = {name: entry.model_dump() for name, entry in config.items()}
        atomic_write_text(self.commands_config_path, json.dumps(data, indent=2))

    def save_endpoint_config(self, project_name: str, config: EndpointConfig) -> None:
        """Save endpoint configuration atomically."""
        config_path = self._project_paths(project_name).endpoint_config_json(
            config.repo_name
        )
        atomic_write_text(config_path, json.dumps(config.model_dump(), indent=2))

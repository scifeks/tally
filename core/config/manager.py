"""Configuration management for global and project settings."""

import json
from pathlib import Path

from .schemas import (
    CommandEntry,
    EndpointConfig,
    GlobalConfig,
    NmapHostsConfig,
    NmapProfile,
    ProjectConfig,
    Repository,
)


class ConfigManager:
    """Manages global and project-specific configurations."""

    def __init__(self, base_path: str = "."):
        """Initialize config manager.

        Args:
            base_path: Base directory for the application
        """
        self.base_path = Path(base_path)
        self.global_config_path = self.base_path / "config" / "global.json"
        self.projects_dir = self.base_path / "projects"

        self.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.global_config = self._load_global_config()

    def _load_global_config(self) -> GlobalConfig:
        """Load global configuration from disk.

        Raises:
            FileNotFoundError: If config/global.json does not exist.
            ValueError: If required fields (default_llm, default_embedding) are missing.
        """
        if not self.global_config_path.exists():
            raise FileNotFoundError(
                f"Global config not found at {self.global_config_path}. "
                "Create it with the required fields: default_llm, default_embedding."
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
        """Save global configuration to disk.

        Args:
            config: Global configuration to save
        """
        with open(self.global_config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

    def load_project_config(self, project_name: str) -> ProjectConfig | None:
        """Load project configuration.

        Args:
            project_name: Name of the project

        Returns:
            ProjectConfig if exists, None otherwise
        """
        config_path = self.projects_dir / project_name / "config" / "project.json"

        if not config_path.exists():
            return None

        with open(config_path) as f:
            data = json.load(f)
            return ProjectConfig(**data)

    def save_project_config(self, project_name: str, config: ProjectConfig) -> None:
        """Save project configuration.

        Args:
            project_name: Name of the project
            config: Project configuration to save
        """
        config_dir = self.projects_dir / project_name / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "project.json"
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

    def load_nmap_hosts(self, project_name: str) -> NmapHostsConfig | None:
        """Load nmap hosts configuration for a project.

        Args:
            project_name: Name of the project

        Returns:
            NmapHostsConfig, or None if not found
        """
        config_path = self.projects_dir / project_name / "config" / "nmap_hosts.json"

        if not config_path.exists():
            return None

        with open(config_path) as f:
            data = json.load(f)

        excluded = data.pop("excluded_networks", [])
        profiles = {name: NmapProfile(**profile) for name, profile in data.items()}
        return NmapHostsConfig(profiles=profiles, excluded_networks=excluded)

    def save_nmap_hosts(
        self,
        project_name: str,
        profiles: dict[str, NmapProfile],
        excluded_networks: list[str] | None = None,
    ) -> None:
        """Save nmap hosts configuration.

        Args:
            project_name: Name of the project
            profiles: Dictionary of profile name to NmapProfile
            excluded_networks: Optional list of excluded IPs/CIDRs
        """
        config_dir = self.projects_dir / project_name / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "nmap_hosts.json"
        data: dict = {name: profile.model_dump() for name, profile in profiles.items()}
        if excluded_networks:
            data["excluded_networks"] = excluded_networks

        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_repositories(self, project_name: str) -> list[Repository]:
        """Load repositories configuration for a project.

        Args:
            project_name: Name of the project

        Returns:
            List of Repository objects
        """
        config_path = self.projects_dir / project_name / "config" / "repositories.json"

        if not config_path.exists():
            return []

        with open(config_path) as f:
            data = json.load(f)
            return [Repository(**repo) for repo in data.get("repositories", [])]

    def save_repositories(
        self, project_name: str, repositories: list[Repository]
    ) -> None:
        """Save repositories configuration.

        Args:
            project_name: Name of the project
            repositories: List of Repository objects
        """
        config_dir = self.projects_dir / project_name / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "repositories.json"
        data = {"repositories": [repo.model_dump() for repo in repositories]}

        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_endpoint_config(
        self, project_name: str, repo_name: str
    ) -> EndpointConfig | None:
        """Load endpoint configuration for a repository.

        Args:
            project_name: Name of the project
            repo_name: Name of the repository

        Returns:
            EndpointConfig if exists, None otherwise
        """
        config_path = (
            self.projects_dir
            / project_name
            / "config"
            / "endpoints"
            / f"{repo_name}.json"
        )

        if not config_path.exists():
            return None

        with open(config_path) as f:
            data = json.load(f)
            return EndpointConfig(**data)

    def load_commands_config(self) -> dict[str, CommandEntry] | None:
        """Load commands.json from the app config directory.

        Returns:
            Dict mapping tool name to CommandEntry, or None if file does not exist.
        """
        config_path = self.base_path / "config" / "commands.json"
        if not config_path.exists():
            return None
        with open(config_path) as f:
            data = json.load(f)
        return {name: CommandEntry(**entry) for name, entry in data.items()}

    def save_commands_config(self, config: dict[str, CommandEntry]) -> None:
        """Save commands.json to the app config directory.

        Args:
            config: Dict mapping tool name to CommandEntry
        """
        config_path = self.base_path / "config" / "commands.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: entry.model_dump() for name, entry in config.items()}
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

    def save_endpoint_config(self, project_name: str, config: EndpointConfig) -> None:
        """Save endpoint configuration for a repository.

        Args:
            project_name: Name of the project
            config: EndpointConfig to save
        """
        config_dir = self.projects_dir / project_name / "config" / "endpoints"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / f"{config.repo_name}.json"
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

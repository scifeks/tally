"""Project path conventions — single source for `projects/<name>/...` layout."""

from __future__ import annotations

from pathlib import Path


class ProjectPaths:
    """Named accessors for the on-disk layout of a single project root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def sqlite_dir(self) -> Path:
        return self.root / "sqlite"

    @property
    def findings_db(self) -> Path:
        return self.sqlite_dir / "findings.db"

    @property
    def chroma_db(self) -> Path:
        return self.root / "chroma_db"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def config_json(self) -> Path:
        return self.config_dir / "project.json"

    @property
    def commands_json(self) -> Path:
        return self.config_dir / "commands.json"

    @property
    def endpoints_config_dir(self) -> Path:
        return self.config_dir / "endpoints"

    def endpoint_config_json(self, repo: str) -> Path:
        return self.endpoints_config_dir / f"{repo}.json"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def reports_draft_dir(self) -> Path:
        return self.reports_dir / "draft"

    @property
    def tool_outputs_dir(self) -> Path:
        return self.root / "tool_outputs"

    def tool_output_dir(self, tool: str) -> Path:
        return self.tool_outputs_dir / tool

    @property
    def endpoints_dir(self) -> Path:
        return self.root / "endpoints"

    def endpoint_dir(self, repo: str) -> Path:
        return self.endpoints_dir / repo

    @property
    def endpoints_original_dir(self) -> Path:
        return self.endpoints_dir / "original"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @classmethod
    def from_registry_row(cls, row: dict) -> ProjectPaths:
        """Build a ProjectPaths from a registry result row."""
        return cls(Path(row["path"]))

    @classmethod
    def projects_dir(cls, base_path: Path | str) -> Path:
        """Return the projects directory `<base_path>/projects/`.

        Single source of truth for the projects-subdir convention.
        """
        return Path(base_path) / "projects"

    @classmethod
    def active_file(cls, base_path: Path | str) -> Path:
        """Return the active-project marker file `<base_path>/projects/.active`."""
        return cls.projects_dir(base_path) / ".active"

    @classmethod
    def from_canonical(cls, base_path: Path | str, name: str) -> ProjectPaths:
        """Build a ProjectPaths at the canonical `<base_path>/projects/<name>/`.

        Use registry resolution (`from_registry_row`) when the project's path
        may have drifted; use this when you need the canonical location.
        """
        return cls(cls.projects_dir(base_path) / name)

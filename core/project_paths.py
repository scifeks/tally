"""Project path conventions: single source for `projects/<name>/...` layout."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.projects.entry import ProjectRow


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
    def garak_config_dir(self) -> Path:
        return self.config_dir / "garak"

    def garak_config(self, repo_id: int) -> Path:
        return self.garak_config_dir / str(repo_id) / "garak.yaml"

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
        """Return ``endpoints/<repo>/`` for JIT-rebuilt merged artifacts.

        Keyed on the integer repo id (callers pass ``str(repo_id)``).
        ``merged_urls.txt`` and ``merged_oas3.json`` live inside it.
        """
        return self.endpoints_dir / repo

    @property
    def arg_files_dir(self) -> Path:
        return self.root / "arg_files"

    def arg_profile_dir(self, profile_id: int) -> Path:
        return self.arg_files_dir / str(profile_id)

    def seed_upload_dir(self, repo_name: str, epoch: int) -> Path:
        """Return ``endpoints/<repo_name>-<epoch>/`` for a user upload.

        Each upload creates a fresh sibling dir so prior uploads aren't
        clobbered; the most-recent path is persisted in
        ``repositories.url_seed_file`` for future history features.
        """
        return self.endpoints_dir / f"{repo_name}-{epoch}"

    @property
    def endpoints_original_dir(self) -> Path:
        return self.endpoints_dir / "original"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @classmethod
    def from_registry_row(cls, row: ProjectRow) -> ProjectPaths:
        """Build a ProjectPaths from a registry result row."""
        return cls(Path(row.path))

    @classmethod
    def projects_dir(cls, base_path: Path | str) -> Path:
        """Return the projects directory `<base_path>/projects/`.

        Single source of truth for the projects-subdir convention.
        """
        return Path(base_path) / "projects"

    @classmethod
    def from_canonical(cls, base_path: Path | str, name: str) -> ProjectPaths:
        """Build a ProjectPaths at the canonical `<base_path>/projects/<name>/`.

        Use registry resolution (`from_registry_row`) when the project's path
        may have drifted; use this when you need the canonical location.
        """
        return cls(cls.projects_dir(base_path) / name)

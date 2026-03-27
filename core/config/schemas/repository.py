"""Repository schema."""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

_VALID_REPO_TYPES: frozenset[str] = frozenset({"library", "api", "ui"})


class Repository(BaseModel):
    """Repository configuration."""

    name: str = Field(..., description="Repository name")
    type: list[str] = Field(..., description="Repository types (library, api, ui)")
    path: str = Field(default="", description="Filesystem path to repository")
    docker_path: str = Field(
        default="", description="Container mount path for Docker tools"
    )
    container_name: str = Field(
        default="", description="Docker container name for docker-mode tools"
    )
    languages: list[str] = Field(..., description="Programming languages used")
    base_urls: list[str] = Field(default_factory=list, description="API base URLs")
    test_dirs: list[str] = Field(
        default_factory=list,
        description=(
            "Dir names to treat as test directories. Matched by name at any depth "
            "in the tree (e.g. 'tests' excludes src/module/tests/). "
            "Case-insensitive. Used to exclude test code from scan findings."
        ),
    )
    ignore_dirs: list[str] = Field(
        default_factory=list,
        description=(
            "Dir names to exclude from scans. Matched by name at any depth "
            "in the tree (e.g. 'vendor' excludes app/vendor/). "
            "Case-insensitive. Applies to SAST and secrets tool segments."
        ),
    )

    @field_validator("type")
    @classmethod
    def validate_repo_type(cls, v: list[str]) -> list[str]:
        """Validate repository type values and mutual exclusivity."""
        if not v:
            raise ValueError("At least one repository type is required")
        invalid = set(v) - _VALID_REPO_TYPES
        if invalid:
            sorted_invalid = ", ".join(sorted(invalid))
            raise ValueError(
                f"Invalid type(s): {sorted_invalid}. Valid: library, api, ui"
            )
        if "library" in v and len(v) > 1:
            raise ValueError("'library' cannot be combined with other types")
        return v

    @field_validator("path")
    @classmethod
    def path_must_exist(cls, v: str) -> str:
        """Validate that repository path exists (only when non-empty)."""
        if v and not Path(v).exists():
            raise ValueError(f"Repository path does not exist: {v}")
        return v

    @model_validator(mode="after")
    def validate_paths(self) -> "Repository":
        if not self.path and not self.docker_path:
            raise ValueError("At least one of 'path' or 'docker_path' must be set")
        if self.docker_path and not self.container_name:
            raise ValueError("'container_name' is required when 'docker_path' is set")
        return self


def build_excluded_dirs(repo: Repository) -> list[str]:
    """Return deduplicated list of dir names to exclude from scans.

    Combines repo.test_dirs and repo.ignore_dirs, preserving insertion order.
    Callers (tool wrappers, ingestor) should treat entries as bare dir names
    matched case-insensitively at any depth in the file tree.
    """
    return list(dict.fromkeys(repo.test_dirs + repo.ignore_dirs))

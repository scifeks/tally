"""RepoService schema for multi-service repositories."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_SERVICE_TYPES: frozenset[str] = frozenset({"library", "api", "ui"})


class RepoService(BaseModel):
    """Configuration for a single service within a repository."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Service name")
    relative_path: str = Field(
        default="", description="Path relative to repository root"
    )
    type: list[str] = Field(
        default_factory=list,
        description="Service types (library, api, ui). Empty list allowed.",
    )
    languages: list[str] = Field(
        default_factory=list, description="Programming languages used"
    )
    docker_path: str = Field(
        default="", description="Container mount path for Docker tools"
    )
    container_name: str = Field(
        default="", description="Docker container name for docker-mode tools"
    )
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
            "Case-insensitive. Applies to SAST and secrets tool segments, "
            "and to URL discovery (Noir, Katana) at the inventory ingest "
            "boundary. Vendor-style names listed here are excluded from "
            "url_findings on top of the built-in indicators."
        ),
    )
    dependencies_file: str = Field(
        default="",
        description=(
            "Path to the Python dependencies file used to scope pip-audit. "
            "For docker services, use the container-internal path "
            "(e.g. /app/requirements.txt). For local services, a local filesystem "
            "path (e.g. requirements.txt). When absent, pip-audit is skipped "
            "for local services; docker services fall back to a full environment "
            "scan."
        ),
    )
    crawl_enabled: bool = Field(
        default=True,
        description=(
            "When False, Katana and Noir are skipped entirely for this "
            "service. Set to False when the user provides their own "
            "endpoint file and opts out of live crawling."
        ),
    )
    katana_headless: bool | None = Field(
        default=None,
        description="Override repo-level headless setting for this service.",
    )
    katana_depth: int | None = Field(
        default=None,
        ge=0,
        le=20,
        description="Override repo-level crawl depth for this service.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is non-empty."""
        if not v or not v.strip():
            raise ValueError("Service name must be non-empty")
        return v

    @field_validator("type")
    @classmethod
    def validate_service_type(cls, v: list[str]) -> list[str]:
        """Validate service type values and mutual exclusivity."""
        if not v:
            return v
        invalid = set(v) - _VALID_SERVICE_TYPES
        if invalid:
            sorted_invalid = ", ".join(sorted(invalid))
            raise ValueError(
                f"Invalid type(s): {sorted_invalid}. Valid: library, api, ui"
            )
        if "library" in v and len(v) > 1:
            raise ValueError("'library' cannot be combined with other types")
        return v

    @model_validator(mode="after")
    def validate_docker_requirement(self) -> "RepoService":
        """Validate docker_path and container_name relationship."""
        if self.docker_path and not self.container_name:
            raise ValueError("'container_name' is required when 'docker_path' is set")
        return self

    @model_validator(mode="after")
    def cap_headless_depth(self) -> "RepoService":
        """Cap crawl depth at 5 when headless is enabled."""
        if self.katana_headless and self.katana_depth is not None:
            self.katana_depth = min(self.katana_depth, 5)
        return self

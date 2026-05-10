"""Repository schema."""

import warnings
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_REPO_TYPES: frozenset[str] = frozenset({"library", "api", "ui"})


class RepoAuth(BaseModel):
    """Optional auth config for repos that require login before crawling.

    Credential resolution order: ``credentials_env`` env var (format
    ``user:pass``) takes precedence over inline ``username`` / ``password``.
    """

    login_url: str = Field(..., description="Full URL of the login form endpoint")
    username_field: str = Field(
        default="username", description="Name attribute of the username input"
    )
    password_field: str = Field(
        default="password", description="Name attribute of the password input"
    )
    extra_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Additional form fields (e.g. submit button values)",
    )
    credentials_env: str = Field(
        default="",
        description=(
            "Env var containing credentials as 'user:pass'. "
            "Takes precedence over inline username/password when set."
        ),
    )
    username: str = Field(default="", description="Inline username (fallback)")
    password: str = Field(default="", description="Inline password (fallback)")


class Repository(BaseModel):
    """Repository configuration."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Repository name (mutable label)")
    id: int | None = Field(
        default=None,
        description=(
            "Integer primary key from the ``repositories`` table. ``None`` "
            "on freshly-built instances that have not been persisted yet."
        ),
        exclude=True,
    )
    url_seed_file: str | None = Field(
        default=None,
        description=(
            "Absolute path to the most-recent user-uploaded endpoint file "
            "for this repo, or ``None`` when no upload has occurred. "
            "Populated by the DB row builder."
        ),
        exclude=True,
    )
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
            "For docker repos, use the container-internal path "
            "(e.g. /app/requirements.txt). For local repos, a local filesystem "
            "path (e.g. requirements.txt). When absent, pip-audit is skipped "
            "for local repos; docker repos fall back to a full environment scan."
        ),
    )
    crawl_enabled: bool = Field(
        default=True,
        description=(
            "When False, Katana and Noir are skipped entirely for this "
            "repository. Set to False when the user provides their own "
            "endpoint file and opts out of live crawling."
        ),
    )
    xsstrike_crawl_level: int = Field(
        default=10,
        description=(
            "XSStrike crawl depth level passed as -l. Default 10 ensures "
            "deeply nested pages are reached. Reduce for faster scans on "
            "shallow apps."
        ),
    )
    xsstrike_headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Extra HTTP headers passed to XSStrike via --headers (JSON "
            "serialised). Use to supply authentication cookies, e.g. "
            '{"Cookie": "session=abc123"}.'
        ),
    )
    dalfox_headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Extra HTTP headers passed to DalFox via -H. Use to supply "
            'authentication cookies, e.g. {"Cookie": "session=abc123"}.'
        ),
    )
    katana_headless: bool = Field(
        default=False,
        description=(
            "Enable headless Chrome mode for Katana. Slower but discovers "
            "JavaScript-rendered routes and SPA endpoints. Recommended for "
            "Node.js and SPA applications."
        ),
    )
    katana_depth: int = Field(
        default=5,
        description=(
            "Katana crawl depth (-d flag). Default 5. Headless mode caps this "
            "at 5 automatically; deeper headless crawls stall on cyclic or "
            "parameterised apps and offer diminishing returns."
        ),
    )
    katana_headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Extra HTTP headers passed to Katana via -H. Use for "
            "authentication cookies or custom user agents, e.g. "
            '{"Cookie": "session=abc123"}.'
        ),
    )
    auth: RepoAuth | None = Field(
        default=None,
        description=(
            "Optional login config. When set, Tally performs a pre-crawl "
            "login (POST to login_url), extracts the session cookie, and "
            "injects it into Katana headers automatically."
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

    @model_validator(mode="after")
    def cap_headless_depth(self) -> "Repository":
        """Cap katana_depth at 5 when headless mode is enabled.

        Headless Chrome at high depth stalls indefinitely on cyclic or
        parameterised apps (e.g. DVWA ``?id=...``). Silently truncating
        rather than raising allows existing project configs to load.
        """
        _HEADLESS_DEPTH_CAP = 5
        if self.katana_headless and self.katana_depth > _HEADLESS_DEPTH_CAP:
            warnings.warn(
                f"katana_depth={self.katana_depth} with headless=True is "
                f"capped to {_HEADLESS_DEPTH_CAP} to prevent infinite crawls.",
                UserWarning,
                stacklevel=2,
            )
            self.katana_depth = _HEADLESS_DEPTH_CAP
        return self


def build_excluded_dirs(repo: Repository) -> list[str]:
    """Return deduplicated list of dir names to exclude from scans.

    Combines repo.test_dirs and repo.ignore_dirs in insertion order. Entries
    are bare dir names matched case-insensitively at any depth in the tree.
    """
    return list(dict.fromkeys(repo.test_dirs + repo.ignore_dirs))

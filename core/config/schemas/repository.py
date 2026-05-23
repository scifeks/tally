"""Repository schema."""

import warnings
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .repo_service import RepoService

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
    path: str = Field(default="", description="Filesystem path to repository")
    services: list[RepoService] = Field(
        default_factory=list, description="Services within this repository"
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
    sqlmap_level: int = Field(
        default=2,
        description=(
            "sqlmap detection level (1-5). Higher levels test more "
            "payloads and injection points but take longer. Level 2 "
            "adds cookie and additional parameter testing."
        ),
    )
    sqlmap_risk: int = Field(
        default=2,
        description=(
            "sqlmap risk level (1-3). Higher risk enables heavier "
            "payloads (e.g. OR-based injections at risk 3 can alter "
            "data). Risk 2 adds time-based blind testing while "
            "remaining safe for production targets."
        ),
    )
    sqlmap_headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Extra HTTP headers passed to sqlmap via --header. Use "
            "to supply authentication cookies, e.g. "
            '{"Cookie": "session=abc123"}.'
        ),
    )
    sqlmap_tamper: str = Field(
        default="",
        description=(
            "Comma-separated tamper script names for WAF evasion "
            "(e.g. 'space2comment,between'). Leave empty for "
            "default payloads."
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

    @field_validator("path")
    @classmethod
    def path_must_exist(cls, v: str) -> str:
        if v and not Path(v).exists():
            raise ValueError(f"Repository path does not exist: {v}")
        return v

    @model_validator(mode="after")
    def validate_services_required(self) -> "Repository":
        if not self.services:
            raise ValueError("At least one service is required")
        return self

    @model_validator(mode="after")
    def cap_headless_depth(self) -> "Repository":
        # Headless Chrome stalls on cyclic apps at high depth.

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


def build_excluded_dirs(service: RepoService) -> list[str]:
    """Return deduplicated list of dir names to exclude from scans.

    Combines service.test_dirs and service.ignore_dirs in insertion order.
    Entries are bare dir names matched case-insensitively at any depth in the
    tree.
    """
    return list(dict.fromkeys(service.test_dirs + service.ignore_dirs))

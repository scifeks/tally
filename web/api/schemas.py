"""Pydantic request and response models for the findings API."""

from __future__ import annotations

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
    STATUS_LEVELS,
)


class FindingPatchRequest(BaseModel):
    """Partial-update request body for PATCH /api/findings/{id}.

    Only fields explicitly included in the request are written.
    Locked fields (url, id, fingerprint, tool, etc.) are silently
    ignored if sent by the client (``extra="ignore"``).
    ``triaged_at`` and ``triaged_by`` are set automatically by the
    server on every successful PATCH.
    """

    model_config = ConfigDict(extra="ignore")

    # Editable named columns
    severity: str | None = None
    confidence: str | None = None
    finding_type: list[str] | None = None
    description: str | None = None
    status: str | None = None
    should_report: bool | None = None
    business_impact: str | None = None
    tal_id: str | None = None
    cwe: list[str] | None = None

    # Editable meta keys — meta_ prefix maps to the meta blob key
    meta_remediation: str | None = None
    meta_risk_type: str | None = None
    meta_owasp_name: str | None = None
    title: str | None = Field(
        default=None,
        validation_alias=AliasChoices("title", "meta_title"),
    )
    meta_tags: list[str] | None = None
    notes: str | None = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is not None and v not in SEVERITY_LEVELS:
            raise ValueError(f"severity must be one of {sorted(SEVERITY_LEVELS)}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str | None) -> str | None:
        if v is not None and v not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
        return v

    @field_validator("finding_type")
    @classmethod
    def validate_finding_type(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for item in v:
                if item not in FINDING_TYPES:
                    raise ValueError(
                        f"finding_type values must be one of {sorted(FINDING_TYPES)}"
                    )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in STATUS_LEVELS:
            raise ValueError(f"status must be one of {sorted(STATUS_LEVELS)}")
        return v


class BatchFindingPatchRequest(BaseModel):
    """Batch-update request body for PATCH /api/findings/batch.

    Applies the same field-level updates to every finding ID in ``ids``.
    At least one field besides ``ids`` must be present.
    ``triaged_at`` and ``triaged_by`` are set automatically on every write.
    Meta keys (meta_*) are not supported for batch updates.
    """

    model_config = ConfigDict(extra="ignore")

    ids: list[int]
    should_report: bool | None = None
    status: str | None = None
    severity: str | None = None
    confidence: str | None = None
    description: str | None = None
    business_impact: str | None = None
    tal_id: str | None = None

    @field_validator("ids")
    @classmethod
    def validate_ids_nonempty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ids must not be empty")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is not None and v not in SEVERITY_LEVELS:
            raise ValueError(f"severity must be one of {sorted(SEVERITY_LEVELS)}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str | None) -> str | None:
        if v is not None and v not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in STATUS_LEVELS:
            raise ValueError(f"status must be one of {sorted(STATUS_LEVELS)}")
        return v

    @model_validator(mode="after")
    def validate_has_patch_fields(self) -> BatchFindingPatchRequest:
        fields = self.model_dump(exclude={"ids"}, exclude_none=True)
        if not fields:
            raise ValueError("at least one field besides ids is required")
        return self


class FindingResponse(BaseModel):
    """Serialised finding returned by the findings API.

    Defined as a permissive model to accommodate the dynamic ``meta``
    JSON blob and per-tool optional fields.
    """

    model_config = ConfigDict(extra="allow")

    is_locked: bool = False
    lock_holder: str | None = None


class FindingsListResponse(BaseModel):
    items: list[FindingResponse]
    total: int
    offset: int
    limit: int


class BatchPatchResponse(BaseModel):
    """Response for PATCH /api/v1/findings/batch.

    Three disjoint id buckets:
    - ``updated``: ids successfully written.
    - ``skipped_locked``: ids held by another job at request time.
    - ``not_found``: ids that do not exist.
    ``skip_reasons`` maps skipped-locked ids to the string
    ``"FINDING_LOCKED"``.
    """

    updated: list[int]
    skipped_locked: list[int]
    not_found: list[int]
    skip_reasons: dict[int, str]


class ProjectListItem(BaseModel):
    id: int
    name: str
    code: str
    created_at: str
    is_active: bool


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem]
    total: int
    offset: int
    limit: int


class ProjectMetaResponse(BaseModel):
    id: int
    name: str
    code: str
    repo_count: int
    url_list_count: int
    finding_count: int


class ProjectInfoResponse(BaseModel):
    id: int
    name: str
    code: str
    company: str
    department: str
    abbreviation: str
    created_at: str
    path: str
    repo_count: int
    finding_count: int


class RepositoryItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: list[str]
    path: str | None = None
    docker_path: str | None = None
    container_name: str | None = None
    languages: list[str]
    base_urls: list[str]


class RepositoryListResponse(BaseModel):
    items: list[RepositoryItem]
    total: int
    offset: int
    limit: int


class DockerContainerResponse(BaseModel):
    name: str
    tool_path: str


class ToolCatalogItem(BaseModel):
    id: str
    name: str
    domain: str
    supports_local: bool
    supports_docker: bool
    description: str


class ToolCatalogResponse(BaseModel):
    items: list[ToolCatalogItem]
    total: int


class ToolOverrideItem(BaseModel):
    tool_id: str
    type: str
    location: str
    path: str | None = None
    container: DockerContainerResponse | None = None


class ToolOverrideResponse(BaseModel):
    items: list[ToolOverrideItem]
    total: int


class RuntimeDependencyItem(BaseModel):
    name: str
    installed: bool
    binary_path: str | None
    version: str | None
    install_hint: str
    required_for: list[str]
    error: str | None


class RuntimeDependenciesResponse(BaseModel):
    dependencies: list[RuntimeDependencyItem]

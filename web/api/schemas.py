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

    # Editable meta keys: meta_ prefix maps to the meta blob key
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
    enabled_tools: list[str]


class ProjectInfoResponse(BaseModel):
    id: int
    name: str
    code: str
    company_name: str
    department_name: str
    abbreviation: str
    created_at: str
    path: str
    repo_count: int
    finding_count: int


class ProjectInfoPatchRequest(BaseModel):
    """Mutable subset of project info; name and created are immutable."""

    company_name: str | None = None
    department_name: str | None = None
    abbreviation: str | None = Field(default=None, max_length=3)


class RepositoryItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    name: str
    type: list[str]
    path: str | None = None
    docker_path: str | None = None
    container_name: str | None = None
    languages: list[str]
    base_urls: list[str]
    endpoint_file: str | None = None


class RepoAuthPatchRequest(BaseModel):
    """JSON body for PATCH /repositories/:repo_id/auth.

    All fields optional; provided values overwrite the auth block.
    """

    model_config = ConfigDict(extra="allow")

    login_url: str | None = None
    username_field: str | None = None
    password_field: str | None = None
    extra_fields: dict[str, str] | None = None
    credentials_env: str | None = None
    username: str | None = None
    password: str | None = None


class RepositoryListResponse(BaseModel):
    items: list[RepositoryItem]
    total: int
    offset: int
    limit: int


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


class InstalledToolsResponse(BaseModel):
    """Names of tool wrappers whose binary was probed at process startup."""

    installed: list[str]


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


class CapabilitiesResponse(BaseModel):
    chat_enabled: bool
    triage_enabled: bool
    report_retention_enabled: bool
    max_report_history: int


class FindingHistoryItem(BaseModel):
    id: int
    finding_id: int
    timestamp: str
    before_values: dict
    after_values: dict
    inference_context: dict | None = None
    source: str


class FindingHistoryResponse(BaseModel):
    items: list[FindingHistoryItem]
    total: int
    offset: int
    limit: int


class FindingsCountsResponse(BaseModel):
    by_severity: dict[str, int]
    by_domain: dict[str, int]
    by_segment: dict[str, int]
    by_repo: dict[str, int]
    by_status: dict[str, int]
    by_tool: dict[str, int]
    by_severity_status: dict[str, dict[str, int]]
    total: int
    scans_count: int
    repos_count: int
    urls_count: int
    last_scan_at: str | None
    last_triage_at: str | None


class FindingsFacetsResponse(BaseModel):
    domains: list[str]
    severities: list[str]
    statuses: list[str]
    confidence_levels: list[str]
    finding_types: list[str]
    tools: list[str]
    repos: list[str]
    segments: list[str]


class FilterOption(BaseModel):
    """One value/count pair for a Findings filter dropdown."""

    value: str
    count: int


class RepoFilterOption(BaseModel):
    """Repo dropdown option. ``value`` is the integer repo id used by
    the filter param; ``label`` is the human-readable repo name shown in
    the UI.
    """

    value: int
    label: str
    count: int


class FindingsFilterOptionsResponse(BaseModel):
    """Per-dimension filter options under the active filter set.

    Strict semantics: every dimension's counts apply every active
    filter, including its own dimension's filter. Options with zero
    matches are omitted; every dimension key is always present (empty
    list is allowed).
    """

    severity: list[FilterOption]
    status: list[FilterOption]
    confidence: list[FilterOption]
    domain: list[FilterOption]
    segment: list[FilterOption]
    tool: list[FilterOption]
    finding_type: list[FilterOption]
    repo: list[RepoFilterOption]


class UrlListPortFilterOption(BaseModel):
    """Port dropdown option. ``value`` is an integer port number."""

    value: int
    count: int


class UrlListFilterOptionsResponse(BaseModel):
    """Per-dimension filter options for the URL Lists page (Phase 12.2).

    Strict semantics (same as Findings): every dimension's counts apply
    every active filter, including its own dimension's filter. Zero-count
    options are omitted; every dimension key is always present (empty
    list is allowed). ``port`` values are integers; ``repo`` entries
    carry a ``label`` (repo name) since the filter param is ``repo_id``.
    """

    method: list[FilterOption]
    protocol: list[FilterOption]
    host: list[FilterOption]
    port: list[UrlListPortFilterOption]
    path: list[FilterOption]
    repo: list[RepoFilterOption]


class ScanConfigRepo(BaseModel):
    id: int
    name: str
    source: str
    location: str | None = None


class ScanConfigTool(BaseModel):
    id: str
    name: str
    domain: str
    enabled: bool = True


class ScanConfigResponse(BaseModel):
    repos: list[ScanConfigRepo]
    tools: list[ScanConfigTool]
    domains: list[str]


class ScanStartRequest(BaseModel):
    """POST body for /api/v1/projects/{id}/scans.

    All fields optional; empty arrays mean "scan everything" per
    endpoints.md §9. Field names are camelCase to match the SSE/HTTP
    contract; aliases accept snake_case for REPL/tooling parity.
    The argProfileIds field (D-1-4) is additive: existing callers that
    omit it continue to work unchanged.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    repoIds: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("repoIds", "repo_ids"),
    )
    toolIds: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("toolIds", "tool_ids"),
    )
    domains: list[str] = Field(default_factory=list)
    skipToolIds: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("skipToolIds", "skip_tool_ids"),
    )
    skipEnrichment: bool = Field(
        default=False,
        validation_alias=AliasChoices("skipEnrichment", "skip_enrichment"),
    )
    argProfileIds: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("argProfileIds", "arg_profile_ids"),
    )


class ScanRunSummary(BaseModel):
    id: int
    project_id: int | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    repo_ids: list[str]
    tool_ids: list[str]
    domains: list[str]
    findings_count: int | None
    skip_enrichment: bool


class ScansListResponse(BaseModel):
    items: list[ScanRunSummary]
    total: int
    offset: int
    limit: int


class ToolRunItem(BaseModel):
    id: int
    run_id: int
    tool: str | None
    repo: str | None
    domain: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    duration: float | None
    findings_count: int
    enriched_count: int | None
    total_to_enrich: int | None
    exit_code: int | None
    skip_reason: str | None


class ScanDetailResponse(BaseModel):
    id: int
    project_id: int | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    repo_ids: list[str]
    tool_ids: list[str]
    domains: list[str]
    findings_count: int | None
    skip_enrichment: bool
    tool_runs: list[ToolRunItem]


class ScanCancelResponse(BaseModel):
    id: int
    status: str


class ScanCancelAllResponse(BaseModel):
    cancelled: list[int]


class ToolRunsSummary(BaseModel):
    queued: int
    running: int
    done: int
    failed: int
    skipped: int


class ScanProgressResponse(BaseModel):
    id: int
    status: str | None
    progress: int
    current_segment: str | None
    segment_label: str | None
    tool_runs_summary: ToolRunsSummary


class TriageStartRequest(BaseModel):
    """POST body for /api/v1/projects/{id}/triage.

    ``acknowledge_injection_risk`` must be ``true`` to confirm the risk.
    ``finding_ids`` is reserved for future finding-scoped triage; if
    omitted or null, the runner queues every untriaged active finding
    for the latest scan_run.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    acknowledge_injection_risk: bool = Field(
        validation_alias=AliasChoices(
            "acknowledge_injection_risk",
            "acknowledgeInjectionRisk",
        ),
    )
    finding_ids: list[int] | None = Field(
        default=None,
        validation_alias=AliasChoices("finding_ids", "findingIds"),
    )


class TriageRunSummary(BaseModel):
    scan_run_id: int
    project_id: int | None
    status: str
    started_at: str | None
    finished_at: str | None
    total_findings: int
    processed_findings: int


class TriagesListResponse(BaseModel):
    items: list[TriageRunSummary]
    total: int
    offset: int
    limit: int


class TriageBatchItem(BaseModel):
    id: int
    scan_run_id: int
    segment: str | None
    finding_ids: list[int]
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
    response_preview: str | None
    error: str | None


class TriageDetailResponse(BaseModel):
    scan_run_id: int
    project_id: int | None
    status: str
    started_at: str | None
    finished_at: str | None
    total_findings: int
    processed_findings: int
    batches: list[TriageBatchItem]


class TriageCancelResponse(BaseModel):
    scan_run_id: int
    status: str


class ReportGenerateRequest(BaseModel):
    """POST body for /api/v1/projects/{id}/reports/generate."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    format: str = Field(default="pdf")
    testing_type: str = Field(
        default="white_box",
        validation_alias=AliasChoices("testing_type", "testingType"),
    )
    engagement_date: str | None = Field(
        default=None,
        validation_alias=AliasChoices("engagement_date", "engagementDate"),
    )
    output_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("output_path", "outputPath"),
    )
    force_overwrite: bool = Field(
        default=False,
        validation_alias=AliasChoices("force_overwrite", "forceOverwrite"),
    )
    company_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("company_name", "companyName"),
    )
    skip_triage: bool = Field(
        default=False,
        validation_alias=AliasChoices("skip_triage", "skipTriage"),
    )

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        valid = {"pdf", "markdown", "html", "json"}
        if v not in valid:
            raise ValueError(f"format must be one of {sorted(valid)}")
        return v

    @field_validator("testing_type")
    @classmethod
    def validate_testing_type(cls, v: str) -> str:
        valid = {"white_box", "grey_box", "black_box"}
        if v not in valid:
            raise ValueError(f"testing_type must be one of {sorted(valid)}")
        return v


class ReportSummary(BaseModel):
    id: int
    project_id: int | None
    scan_run_id: int | None
    format: str
    filename: str
    status: str
    pinned: bool
    file_size_bytes: int | None
    error: str | None
    created_at: str | None
    started_at: str | None
    finished_at: str | None
    download_url: str | None


class ReportsListResponse(BaseModel):
    items: list[ReportSummary]
    total: int
    offset: int
    limit: int


class ReportCancelResponse(BaseModel):
    id: int
    status: str


class ChatSessionSummary(BaseModel):
    """Per-session response payload for GET/POST /chat/sessions.

    ``last_message_at`` and ``message_count`` are derived from
    ``chat_messages`` at read time; they are 0/null on a freshly-created
    session.
    """

    id: int
    project_id: int
    title: str
    created_at: str
    last_message_at: str | None
    message_count: int
    expired_at: str | None


class ChatSessionsListResponse(BaseModel):
    items: list[ChatSessionSummary]
    total: int
    offset: int
    limit: int


class ChatSessionCreateRequest(BaseModel):
    """Body for ``POST /chat/sessions``. Reserved for v2 fields; empty in v1."""

    model_config = ConfigDict(extra="ignore")


class ChatMessageResponse(BaseModel):
    """Per-message response payload for GET .../messages.

    The row column ``created_at`` is surfaced as ``timestamp`` to match
    the SPA contract. ``citations`` is always ``None`` in v1.
    """

    id: int
    session_id: int
    role: str
    content: str
    model: str | None
    timestamp: str
    citations: list[dict] | None = None


class ChatMessagesListResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
    offset: int
    limit: int


class ChatMessageSendRequest(BaseModel):
    """Body for ``POST .../sessions/{session_id}/messages``.

    The ``content`` field carries the user's chat turn. It must be
    non-empty after stripping; the upper bound (100k chars) keeps a
    single user turn well below the 500k prompt-assembly ceiling
    enforced inside ``application.chat.service``.
    """

    model_config = ConfigDict(extra="ignore")

    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def _strip_and_require(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty or whitespace-only")
        return v


class ChatMessageSendResponse(BaseModel):
    """202 response for ``POST .../sessions/{session_id}/messages``.

    ``assistant_message_id`` is ``None`` here because the assistant row
    is written write-once on clean stream end (decisions.md B7.7); the
    final id is delivered via the ``stream_end`` SSE event's
    ``message_id`` field.
    """

    user_message_id: int
    assistant_message_id: int | None
    session_id: int
    stream_url: str


class ChatMessageCancelResponse(BaseModel):
    """202 response for ``POST .../sessions/{session_id}/cancel``.

    ``cancelled_message_id`` is ``None`` in v1 because cancellation lands
    before the ``stream_end`` event where the assistant row would
    otherwise be written write-once (decisions.md B7.7). The field is
    typed ``int | None`` so the wire format stays stable if a future
    iteration assigns the assistant id earlier in the lifecycle.
    """

    session_id: int
    cancelled_message_id: int | None

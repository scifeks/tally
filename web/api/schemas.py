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

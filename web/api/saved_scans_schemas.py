"""Pydantic request and response models for the saved-scans routes.

Wire shape is camelCase per D-1-14. The create and replace bodies share
one model (their wire shape is identical per endpoints.md §4.3 and §4.4).
The route layer enforces existence on replace and surfaces conflicts; the
service layer enforces the at-least-one-non-empty rule and returns
structured FieldError payloads, so this schema does not duplicate those.

The STALE_SAVED_SCAN error envelope payload (D-1-7) lives here as the
discriminated union over the three stale-item kinds, mirroring
domain.saved_scans.entry.StaleSavedScanItem.

No imports from application or infrastructure layers.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class SavedScanWriteRequest(BaseModel):
    """POST /saved-scans and PUT /saved-scans/{id} body."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(min_length=1)
    skip_enrichment: bool = Field(
        default=False,
        validation_alias=AliasChoices("skipEnrichment", "skip_enrichment"),
        serialization_alias="skipEnrichment",
    )
    repo_ids: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("repoIds", "repo_ids"),
        serialization_alias="repoIds",
    )
    tool_names: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("toolNames", "tool_names"),
        serialization_alias="toolNames",
    )
    arg_profile_ids: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("argProfileIds", "arg_profile_ids"),
        serialization_alias="argProfileIds",
    )


class SavedScanListItemResponse(BaseModel):
    """One row in the GET /saved-scans list projection (endpoints.md 4.1)."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    skip_enrichment: bool = Field(serialization_alias="skipEnrichment")
    repo_ids: list[int] = Field(serialization_alias="repoIds")
    tool_names: list[str] = Field(serialization_alias="toolNames")
    arg_profile_ids: list[int] = Field(serialization_alias="argProfileIds")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class SavedScanListResponse(BaseModel):
    """List envelope for GET /saved-scans."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[SavedScanListItemResponse]
    total: int
    offset: int
    limit: int


class SavedScanRepoResponse(BaseModel):
    """Hydrated repo row in GET /saved-scans/{id}."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    deleted_at: str | None = Field(serialization_alias="deletedAt")


class SavedScanToolResponse(BaseModel):
    """Hydrated tool row in GET /saved-scans/{id}."""

    model_config = ConfigDict(populate_by_name=True)

    tool_name: str = Field(serialization_alias="toolName")


class SavedScanArgProfileResponse(BaseModel):
    """Hydrated arg-profile row in GET /saved-scans/{id}."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    tool_name: str = Field(serialization_alias="toolName")
    name: str


class SavedScanDetailResponse(BaseModel):
    """Hydrated saved scan from GET /saved-scans/{id} and POST/PUT."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    skip_enrichment: bool = Field(serialization_alias="skipEnrichment")
    repos: list[SavedScanRepoResponse]
    tools: list[SavedScanToolResponse]
    arg_profiles: list[SavedScanArgProfileResponse] = Field(
        serialization_alias="argProfiles"
    )
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class StaleSavedScanRepoItemDetail(BaseModel):
    """Stale repo entry in the STALE_SAVED_SCAN envelope (D-1-7)."""

    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["repo"] = "repo"
    id: int
    name: str | None = None


class StaleSavedScanToolItemDetail(BaseModel):
    """Stale tool entry in the STALE_SAVED_SCAN envelope (D-1-7)."""

    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["tool"] = "tool"
    name: str


class StaleSavedScanArgProfileItemDetail(BaseModel):
    """Stale arg-profile entry in the STALE_SAVED_SCAN envelope (D-1-7)."""

    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["argProfile"] = "argProfile"
    id: int


StaleSavedScanItemDetail = Annotated[
    StaleSavedScanRepoItemDetail
    | StaleSavedScanToolItemDetail
    | StaleSavedScanArgProfileItemDetail,
    Field(discriminator="kind"),
]


class StaleSavedScanDetails(BaseModel):
    """`details` payload for the 409 STALE_SAVED_SCAN error envelope."""

    model_config = ConfigDict(populate_by_name=True)

    stale_items: list[StaleSavedScanItemDetail] = Field(
        serialization_alias="staleItems"
    )

"""Pydantic request and response models for the arg-profile routes.

The multipart `payload` form field carries JSON that this module parses
into ArgProfilePayload. File bytes arrive as separate UploadFile fields
keyed by sanitized arg name; the route layer pairs them with each
ArgProfilePayloadFileArg before calling the service.

Wire shape is camelCase per D-1-14. No imports from application or
infrastructure layers.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)


class ArgProfilePayloadFlagArg(BaseModel):
    """Flag arg in a multipart payload."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    type: Literal["flag"]


class ArgProfilePayloadStringArg(BaseModel):
    """String arg in a multipart payload."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    value: str
    type: Literal["string"]


class ArgProfilePayloadFileArg(BaseModel):
    """File arg in a multipart payload (bytes arrive in a sibling field)."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    type: Literal["file"]


ArgProfilePayloadArg = Annotated[
    (ArgProfilePayloadFlagArg | ArgProfilePayloadStringArg | ArgProfilePayloadFileArg),
    Field(discriminator="type"),
]


class ArgProfilePayload(BaseModel):
    """JSON parsed out of the multipart `payload` form field."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tool_name: str = Field(
        min_length=1,
        validation_alias=AliasChoices("toolName", "tool_name"),
        serialization_alias="toolName",
    )
    name: str = Field(min_length=1)
    args: list[ArgProfilePayloadArg] = Field(default_factory=list)


def parse_arg_profile_payload(raw: str | None) -> ArgProfilePayload:
    """Parse the multipart `payload` form field into a typed model.

    Raises ValueError on invalid JSON, on a non-object root, or on
    Pydantic validation failure. The route layer maps ValueError to
    422 VALIDATION_ERROR via the standard handler.
    """
    if raw is None or raw == "":
        raise ValueError("payload form field is required")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    try:
        return ArgProfilePayload.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


class ArgProfileFlagArgResponse(BaseModel):
    """Flag arg in a response."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: Literal["flag"] = "flag"


class ArgProfileStringArgResponse(BaseModel):
    """String arg in a response."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    value: str
    type: Literal["string"] = "string"


class ArgProfileFileArgResponse(BaseModel):
    """File arg in a response. download_url is set on the detail endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    path: str
    original_filename: str | None = Field(
        default=None,
        serialization_alias="originalFilename",
    )
    download_url: str | None = Field(
        default=None,
        serialization_alias="downloadUrl",
    )
    type: Literal["file"] = "file"


ArgProfileArgResponse = Annotated[
    (
        ArgProfileFlagArgResponse
        | ArgProfileStringArgResponse
        | ArgProfileFileArgResponse
    ),
    Field(discriminator="type"),
]


class ArgProfileResponse(BaseModel):
    """One arg-profile row as returned by GET endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    tool_name: str = Field(serialization_alias="toolName")
    name: str
    args: list[ArgProfileArgResponse]
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class ArgProfileListResponse(BaseModel):
    """List envelope for GET /arg-profiles."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[ArgProfileResponse]
    total: int
    offset: int
    limit: int


class ArgProfileInUseDetails(BaseModel):
    """`details` payload for the 409 IN_USE error returned by DELETE."""

    model_config = ConfigDict(populate_by_name=True)

    saved_scan_ids: list[int] = Field(serialization_alias="savedScanIds")
    saved_scan_names: list[str] = Field(serialization_alias="savedScanNames")

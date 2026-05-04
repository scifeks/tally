"""Pydantic request and response models for the tool-overrides routes.

Wire shape is camelCase per D-1-14; snake_case aliases let REPL or other
Python callers send the same payloads. No imports from application or
infrastructure layers; these models are pure DTOs at the driving
adapter boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ToolOverrideContainerRequest(BaseModel):
    """Container block for a docker-located override."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(min_length=1)
    tool_path: str = Field(
        min_length=1,
        validation_alias=AliasChoices("toolPath", "tool_path"),
        serialization_alias="toolPath",
    )


class ToolOverrideContainerResponse(BaseModel):
    """Container block as returned in responses."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    tool_path: str = Field(serialization_alias="toolPath")


class ToolOverrideCreateRequest(BaseModel):
    """POST /tools/overrides body."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tool_name: str = Field(
        min_length=1,
        validation_alias=AliasChoices("toolName", "tool_name"),
        serialization_alias="toolName",
    )
    args_mode: Literal["stock", "custom"] = Field(
        validation_alias=AliasChoices("argsMode", "args_mode"),
        serialization_alias="argsMode",
    )
    type: Literal["repo", "api"]
    location: Literal["local", "docker"]
    path: str | None = None
    container: ToolOverrideContainerRequest | None = None


class ToolOverrideReplaceRequest(BaseModel):
    """PUT /tools/overrides/{tool_name} body.

    The path supplies tool_name; if the body also carries it, the route
    layer enforces equality and returns 422 on mismatch.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tool_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("toolName", "tool_name"),
        serialization_alias="toolName",
    )
    args_mode: Literal["stock", "custom"] = Field(
        validation_alias=AliasChoices("argsMode", "args_mode"),
        serialization_alias="argsMode",
    )
    type: Literal["repo", "api"]
    location: Literal["local", "docker"]
    path: str | None = None
    container: ToolOverrideContainerRequest | None = None


class ToolOverrideResponse(BaseModel):
    """One tool-override row as returned by GET endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    tool_name: str = Field(serialization_alias="toolName")
    args_mode: Literal["stock", "custom"] = Field(serialization_alias="argsMode")
    type: Literal["repo", "api"]
    location: Literal["local", "docker"]
    path: str | None = None
    container: ToolOverrideContainerResponse | None = None


class ToolOverrideListResponse(BaseModel):
    """List envelope for GET /tools/overrides."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[ToolOverrideResponse]
    total: int
    offset: int
    limit: int

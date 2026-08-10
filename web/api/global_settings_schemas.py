"""Pydantic request/response models for global settings."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ToolSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ffuf_wordlist_paths: list[str] = Field(
        serialization_alias="ffufWordlistPaths",
    )


class UpdateToolSettingsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    ffuf_wordlist_paths: list[str] = Field(
        validation_alias=AliasChoices("ffufWordlistPaths", "ffuf_wordlist_paths"),
    )


class FileSystemEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    path: str
    is_dir: bool = Field(serialization_alias="isDir")
    size_bytes: int | None = Field(default=None, serialization_alias="sizeBytes")


class FileSystemBrowseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_path: str = Field(serialization_alias="currentPath")
    entries: list[FileSystemEntry]

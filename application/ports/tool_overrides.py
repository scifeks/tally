"""Persistence port for the tool_overrides table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from domain.tool_overrides.entry import ToolOverride


class ToolOverrideNameConflict(Exception):
    """Raised when ``tool_name`` collides with an existing row."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"override for tool {tool_name!r} already exists")
        self.tool_name = tool_name


class ToolOverridesRepositoryPort(Protocol):
    def list_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolOverride], int]: ...
    def get_by_tool_name(self, tool_name: str) -> ToolOverride | None: ...
    def find_service_scoped(
        self,
        tool_name: str,
        repo_id: int,
        service_name: str,
    ) -> ToolOverride | None: ...
    def insert(
        self,
        *,
        tool_name: str,
        args_mode: Literal["stock", "custom"],
        type: Literal["repo", "api"],
        location: Literal["local", "docker"],
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
        scope: Literal["global", "service"] = "global",
        repo_id: int | None = None,
        service_name: str | None = None,
    ) -> int: ...
    def update(
        self,
        tool_name: str,
        *,
        args_mode: Literal["stock", "custom"],
        type: Literal["repo", "api"],
        location: Literal["local", "docker"],
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
        scope: Literal["global", "service"] = "global",
        repo_id: int | None = None,
        service_name: str | None = None,
    ) -> None: ...
    def delete(self, tool_name: str) -> None: ...

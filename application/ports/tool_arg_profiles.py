"""Persistence port for the tool_arg_profiles table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.tool_arg_profiles.entry import ToolArgProfile, ToolArgProfileArg


class ToolArgProfileNameConflict(Exception):
    """Raised when ``(tool_name, name)`` collides with an existing row."""

    def __init__(self, tool_name: str, name: str) -> None:
        super().__init__(f"profile {name!r} already exists for tool {tool_name!r}")
        self.tool_name = tool_name
        self.name = name


class ToolArgProfilesRepositoryPort(Protocol):
    def list_paginated(
        self,
        *,
        tool_name: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolArgProfile], int]: ...
    def get(self, profile_id: int) -> ToolArgProfile | None: ...
    def insert(
        self,
        *,
        tool_name: str,
        name: str,
        args: list[ToolArgProfileArg],
    ) -> int: ...
    def update(
        self,
        profile_id: int,
        *,
        tool_name: str,
        name: str,
        args: list[ToolArgProfileArg],
    ) -> None: ...
    def delete(self, profile_id: int) -> None: ...
    def existing_ids(self, ids: list[int]) -> list[int]: ...

"""Domain entries for per-project tool overrides."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ToolOverride:
    id: int
    tool_name: str
    args_mode: Literal["stock", "custom"]
    type: Literal["repo", "api"]
    location: Literal["local", "docker"]
    path: str | None
    container_name: str | None
    container_tool_path: str | None
    scope: Literal["global", "service"]
    repo_id: int | None
    service_name: str | None
    created_at: str
    updated_at: str

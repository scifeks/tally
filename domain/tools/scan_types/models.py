"""Shared data models for scan types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain.tools.base import ToolResult

if TYPE_CHECKING:
    from application.ports.user_prompt import UserPromptPort
    from core.config.manager import ConfigManager

SEGMENT_ORDER: list[str] = ["sast", "sca", "secrets", "web"]


@dataclass
class ScanSummary:
    total_tools_run: int
    total_tools_skipped: int
    total_tools_failed: int
    results: list[ToolResult]
    duration_seconds: float
    findings_ingested: int
    findings_by_tool: dict[str, int] = field(default_factory=dict)


@dataclass
class ScanTypeConfig:
    project_name: str
    base_path: str
    config_manager: ConfigManager
    run_id: int | None
    prompt: UserPromptPort
    remaining_peers: int = 0
    project_id: int | None = None


@dataclass
class ToolRun:
    tool_interface: object
    profile: str
    remaining: int

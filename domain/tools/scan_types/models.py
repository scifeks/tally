"""Shared data models for scan types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain.pipeline.events import EventBus
from domain.tools.base import ToolResult
from domain.tools.display import OrchestratorDisplay

if TYPE_CHECKING:
    from core.config.manager import ConfigManager

SEGMENT_ORDER: list[str] = ["network", "sast", "sca", "secrets", "api"]


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
    event_bus: EventBus
    display: OrchestratorDisplay
    run_id: int | None
    auto_approve: bool = False


@dataclass
class ToolRun:
    tool_interface: object
    profile: str
    remaining: int

"""Shared data models for scan types."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.tools.base import ToolResult

SEGMENT_ORDER: list[str] = ["sast", "sca", "secrets", "web", "llm"]


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
class ToolRun:
    tool_interface: object
    profile: str
    remaining: int

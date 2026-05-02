"""Domain display contracts and data structures for scan output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ToolDisplayRow:
    tool_name: str
    success: bool
    skipped: bool
    finding_count: int
    duration_seconds: float
    skip_reason: str = ""
    repo: str = ""


@runtime_checkable
class DisplayProtocol(Protocol):
    def print_scan_header(self, label: str) -> None: ...
    def print_segment_header(self, segment: str) -> None: ...
    def print_repo_scan_header(
        self, repo_name: str, lang_str: str, tools: list[str]
    ) -> None: ...
    def print_status(self, message: str) -> None: ...
    def print_running(self, tool_name: str, repo_name: str = "") -> None: ...
    def print_tool_line(self, row: ToolDisplayRow) -> None: ...
    def print_summary_table(self, rows: list[ToolDisplayRow]) -> None: ...
    def print_final_line(
        self, run: int, failed: int, skipped: int, ingested: int, duration: float
    ) -> None: ...


class NullDisplay:
    """Default no-op display. Drops every call."""

    def print_scan_header(self, label: str) -> None:
        del label
        return None

    def print_segment_header(self, segment: str) -> None:
        del segment
        return None

    def print_repo_scan_header(
        self, repo_name: str, lang_str: str, tools: list[str]
    ) -> None:
        del repo_name, lang_str, tools
        return None

    def print_status(self, message: str) -> None:
        del message
        return None

    def print_running(self, tool_name: str, repo_name: str = "") -> None:
        del tool_name, repo_name
        return None

    def print_tool_line(self, row: ToolDisplayRow) -> None:
        del row
        return None

    def print_summary_table(self, rows: list[ToolDisplayRow]) -> None:
        del rows
        return None

    def print_final_line(
        self, run: int, failed: int, skipped: int, ingested: int, duration: float
    ) -> None:
        del run, failed, skipped, ingested, duration
        return None

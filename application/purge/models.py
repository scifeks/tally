"""Domain models for purge operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurgeAnalysis:
    """Result of analyzing what would be purged."""

    chroma_count: int
    sqlite_count: int
    has_tool_outputs: bool
    has_reports: bool
    chat_count: int
    url_count: int

    @property
    def has_anything(self) -> bool:
        """Return True if any findings or artifacts exist to purge."""
        return (
            self.chroma_count > 0
            or self.sqlite_count > 0
            or self.has_tool_outputs
            or self.has_reports
            or self.chat_count > 0
            or self.url_count > 0
        )


@dataclass(frozen=True)
class PurgeResult:
    """Result of a purge execution."""

    chroma_deleted: int
    chat_deleted: int
    reports_deleted: bool
    merged_deleted: bool

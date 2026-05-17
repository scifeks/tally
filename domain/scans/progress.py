"""Domain value objects for scan progress calculation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolRunCounts:
    queued: int
    running: int
    done: int
    failed: int
    skipped: int


@dataclass(frozen=True, slots=True)
class ScanProgress:
    progress: int
    counts: ToolRunCounts

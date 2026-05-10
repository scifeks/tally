"""Domain entry for the global project registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRow:
    id: int
    name: str
    path: str
    created_at: str
    archived_at: str | None = None

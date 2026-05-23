"""Domain-pure lifecycle events for findings."""

from __future__ import annotations

from dataclasses import dataclass

from domain.findings.entry import Finding


@dataclass(frozen=True)
class FindingUpdated:
    """Emitted after a successful analyst PATCH on a single finding."""

    project_id: int
    finding: Finding
    is_locked: bool
    lock_holder: str | None


@dataclass(frozen=True)
class FindingCreated:
    """Emitted after a manual finding is created."""

    project_id: int
    finding: Finding
    is_locked: bool
    lock_holder: str | None


@dataclass(frozen=True)
class FindingDeleted:
    """Emitted after a manual finding is deleted."""

    project_id: int
    finding_id: int

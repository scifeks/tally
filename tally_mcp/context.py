"""Shared dependency context for MCP tool handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.store.repositories.audit import AuditRepository
    from infrastructure.store.repositories.findings import FindingRepository
    from infrastructure.store.repositories.triage import TriageBatchRepository


@dataclass(frozen=True)
class FindingsContext:
    finding_repo: FindingRepository
    audit_repo: AuditRepository
    triage_repo: TriageBatchRepository
    project_name: str

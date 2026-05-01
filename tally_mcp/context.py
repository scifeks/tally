"""Shared dependency context for MCP tool handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.audit_repository import AuditRepositoryPort
    from application.ports.finding_repository import FindingRepositoryPort
    from infrastructure.store.repositories.triage import TriageBatchRepository


@dataclass(frozen=True)
class FindingsContext:
    finding_repo: FindingRepositoryPort
    audit_repo: AuditRepositoryPort
    triage_repo: TriageBatchRepository
    project_name: str

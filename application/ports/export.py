"""Port for exporting findings to external systems."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.findings.entry import Finding


@dataclass(frozen=True)
class ExportResult:
    success: bool
    findings_exported: int
    findings_failed: int
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncRepo:
    id: int
    services: tuple[str, ...]


@dataclass(frozen=True)
class SyncBatch:
    repo_id: int
    tool: str
    findings: tuple[Finding, ...]


class ExportPort(Protocol):
    def export_batches(self, batches: list[SyncBatch]) -> ExportResult: ...

    def test_connection(self) -> bool: ...

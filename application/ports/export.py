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


class ExportPort(Protocol):
    def export_findings(self, findings: list[Finding]) -> ExportResult: ...

    def test_connection(self) -> bool: ...

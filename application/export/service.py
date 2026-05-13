"""Export application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.ports.export import ExportResult

if TYPE_CHECKING:
    from application.ports.export import ExportPort
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )


class ExportService:
    def __init__(
        self,
        finding_repo: FindingRepositoryPort,
        export_adapter: ExportPort,
    ) -> None:
        self._finding_repo = finding_repo
        self._export_adapter = export_adapter

    def export(self, run_id: int | None = None) -> ExportResult:
        if run_id is not None:
            findings = self._finding_repo.get_findings_by_run_id(run_id)
        else:
            findings = self._finding_repo.get_all_findings()

        if not findings:
            return ExportResult(
                success=True,
                findings_exported=0,
                findings_failed=0,
            )

        return self._export_adapter.export_findings(findings)

    def test_connection(self) -> bool:
        return self._export_adapter.test_connection()

"""Export application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.ports.export import ExportResult

if TYPE_CHECKING:
    from application.export.selection import SyncSelector
    from application.ports.export import ExportPort


class ExportService:
    def __init__(
        self,
        selector: SyncSelector,
        export_adapter: ExportPort,
        run_id: int | None = None,
    ) -> None:
        self._selector = selector
        self._export_adapter = export_adapter
        self._run_id = run_id

    def export(self) -> ExportResult:
        batches = self._selector.select(self._run_id)
        if not batches:
            return ExportResult(success=True, findings_exported=0, findings_failed=0)
        return self._export_adapter.export_batches(batches)

    def test_connection(self) -> bool:
        return self._export_adapter.test_connection()

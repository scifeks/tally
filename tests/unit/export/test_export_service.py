"""Unit tests for the export application service."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.export.service import ExportService
from application.ports.export import ExportResult, SyncBatch


class TestExportService:
    def test_sends_the_selected_batches_for_the_given_run(self) -> None:
        selector = MagicMock()
        adapter = MagicMock()
        batches = [SyncBatch(1, "semgrep", ())]
        selector.select.return_value = batches
        adapter.export_batches.return_value = ExportResult(True, 0, 0)

        result = ExportService(selector, adapter, run_id=7).export()

        selector.select.assert_called_once_with(7)
        adapter.export_batches.assert_called_once_with(batches)
        assert result.success is True

    def test_nothing_selected_does_not_reach_the_adapter(self) -> None:
        selector = MagicMock()
        adapter = MagicMock()
        selector.select.return_value = []

        result = ExportService(selector, adapter).export()

        adapter.export_batches.assert_not_called()
        assert result == ExportResult(True, 0, 0)

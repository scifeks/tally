"""Unit tests for export application service."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.export.service import ExportService
from application.ports.export import ExportResult
from domain.findings.entry import Finding


class TestExportService:
    def test_export_all_findings(self) -> None:
        repo = MagicMock()
        export_adapter = MagicMock()

        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        repo.get_all_findings.return_value = [finding]
        export_adapter.export_findings.return_value = ExportResult(
            success=True,
            findings_exported=1,
            findings_failed=0,
        )

        service = ExportService(repo, export_adapter)
        result = service.export(run_id=None)

        repo.get_all_findings.assert_called_once()
        repo.get_findings_by_run_id.assert_not_called()
        export_adapter.export_findings.assert_called_once_with([finding])
        assert result.success is True
        assert result.findings_exported == 1

    def test_export_by_run_id(self) -> None:
        repo = MagicMock()
        export_adapter = MagicMock()

        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=5,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        repo.get_findings_by_run_id.return_value = [finding]
        export_adapter.export_findings.return_value = ExportResult(
            success=True,
            findings_exported=1,
            findings_failed=0,
        )

        service = ExportService(repo, export_adapter)
        result = service.export(run_id=5)

        repo.get_findings_by_run_id.assert_called_once_with(5)
        repo.get_all_findings.assert_not_called()
        export_adapter.export_findings.assert_called_once_with([finding])
        assert result.success is True
        assert result.findings_exported == 1

    def test_export_no_findings_early_return(self) -> None:
        repo = MagicMock()
        export_adapter = MagicMock()

        repo.get_all_findings.return_value = []

        service = ExportService(repo, export_adapter)
        result = service.export(run_id=None)

        repo.get_all_findings.assert_called_once()
        export_adapter.export_findings.assert_not_called()
        assert result.success is True
        assert result.findings_exported == 0
        assert result.findings_failed == 0

    def test_export_no_findings_by_run_id(self) -> None:
        repo = MagicMock()
        export_adapter = MagicMock()

        repo.get_findings_by_run_id.return_value = []

        service = ExportService(repo, export_adapter)
        result = service.export(run_id=10)

        repo.get_findings_by_run_id.assert_called_once_with(10)
        export_adapter.export_findings.assert_not_called()
        assert result.success is True
        assert result.findings_exported == 0
        assert result.findings_failed == 0

    def test_test_connection_delegates(self) -> None:
        repo = MagicMock()
        export_adapter = MagicMock()
        export_adapter.test_connection.return_value = True

        service = ExportService(repo, export_adapter)
        result = service.test_connection()

        export_adapter.test_connection.assert_called_once()
        assert result is True

    def test_test_connection_failure(self) -> None:
        repo = MagicMock()
        export_adapter = MagicMock()
        export_adapter.test_connection.return_value = False

        service = ExportService(repo, export_adapter)
        result = service.test_connection()

        export_adapter.test_connection.assert_called_once()
        assert result is False

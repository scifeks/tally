"""Unit tests for DefectDojo export adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from domain.findings.entry import Finding
from infrastructure.export.defectdojo.adapter import (
    DefectDojoExportAdapter,
)

_CLIENT_PATH = "infrastructure.export.defectdojo.adapter.DefectDojoClient"


def _conn_mock(**overrides: object) -> MagicMock:
    m = MagicMock()
    m.url = overrides.get("url", "http://defectdojo.example.com")
    m.api_token = overrides.get("api_token", "token123")
    m.verify_ssl = overrides.get("verify_ssl", True)
    return m


def _proj_mock(**overrides: object) -> MagicMock:
    m = MagicMock()
    m.product_name = overrides.get("product_name", "TestProduct")
    m.engagement_name = overrides.get("engagement_name", "TestEngage")
    m.product_type_name = overrides.get("product_type_name", "Tally")
    m.auto_create_context = overrides.get("auto_create_context", True)
    return m


def _make_finding(**overrides: object) -> Finding:
    defaults: dict = {
        "id": 1,
        "fingerprint": "fp1",
        "run_id": 1,
        "tool": "test",
        "domain": "code",
        "segment": "sast",
        "severity": "high",
        "confidence": None,
        "description": "Test",
        "file": "test.py",
        "rule_id": "rule1",
        "cwe": [],
        "meta": {},
        "first_seen": "2024-01-15T10:00:00",
        "last_seen": "2024-01-15T10:00:00",
        "seen_count": 1,
        "status": "active",
    }
    defaults.update(overrides)
    return Finding(**defaults)


@patch(_CLIENT_PATH)
class TestDefectDojoExportAdapter:
    def test_export_success(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            200,
            {"engagement_id": 1, "findings_count": 2},
        )

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())
        result = adapter.export_findings([_make_finding()])

        assert result.success is True
        assert result.findings_exported == 1
        assert result.findings_failed == 0

    def test_export_empty_findings(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())
        result = adapter.export_findings([])

        assert result.success is True
        assert result.findings_exported == 0
        assert result.findings_failed == 0
        client.reimport_scan.assert_not_called()

    def test_export_connection_error(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.side_effect = RuntimeError("Network error")

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert len(result.errors) > 0
        assert "Connection error" in result.errors[0]

    def test_export_auth_failure(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            401,
            {"error": "Unauthorized"},
        )

        adapter = DefectDojoExportAdapter(
            _conn_mock(api_token="invalid_token"),
            _proj_mock(),
        )
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert "Authentication failed" in result.errors[0]

    def test_export_forbidden_status(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            403,
            {"error": "Forbidden"},
        )

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert "Authentication failed" in result.errors[0]

    def test_export_bad_request(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            400,
            {"error": "Invalid request format"},
        )

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert len(result.errors) > 0
        assert "400" in result.errors[0]

    def test_test_connection_success(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.test_connection.return_value = True

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())

        assert adapter.test_connection() is True
        client.test_connection.assert_called_once()

    def test_test_connection_failure(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.test_connection.return_value = False

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())

        assert adapter.test_connection() is False
        client.test_connection.assert_called_once()

    def test_export_partial_mapping_failure(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            200,
            {"status": "success"},
        )

        adapter = DefectDojoExportAdapter(_conn_mock(), _proj_mock())
        good = _make_finding(id=1, fingerprint="fp1")
        bad = _make_finding(
            id=2,
            fingerprint="fp2",
            severity=None,
            description=None,
            meta={"bad_meta": "bad_value"},
        )
        result = adapter.export_findings([good, bad])

        assert result.success is True
        assert result.findings_exported >= 1
        assert result.findings_failed >= 0

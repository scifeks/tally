"""Unit tests for ToolHandler normalize() and render() methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.rag.chunks.composer_audit import ComposerAuditChunkBuilder
from application.rag.chunks.gitleaks import GitleaksChunkBuilder
from application.rag.chunks.nmap import NmapChunkBuilder
from application.rag.chunks.npm_audit import NpmAuditChunkBuilder
from application.rag.chunks.osv_scanner import OsvScannerChunkBuilder
from application.rag.chunks.pip_audit import PipAuditChunkBuilder
from application.rag.chunks.semgrep import SemgrepChunkBuilder
from application.rag.chunks.zap import ZapChunkBuilder
from domain.tools.base import ToolResult

_PROFILE = "test"
_TYPE_FLAG_KEYS = frozenset(
    {
        "type_secret",
        "type_vulnerability",
        "type_weakness",
        "type_misconfiguration",
        "type_exposure",
        "type_dependency",
        "type_informational",
    }
)


def _make_result(tool_name: str, parsed_data: dict) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files={},
        timestamp="2024-01-01T00:00:00",
        duration_seconds=0.0,
    )


def _make_result_with_file(
    tool_name: str, parsed_data: dict, output_file: str
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files={"output": Path(output_file)},
        timestamp="2024-01-01T00:00:00",
        duration_seconds=0.0,
    )


# ---------------------------------------------------------------------------
# Gitleaks
# ---------------------------------------------------------------------------


class TestGitleaksHandler:
    _PARSED: dict = {
        "secrets": [
            {
                "rule_id": "aws-access-token",
                "description": "AWS Access Token",
                "file_path": "config/aws.py",
                "line_number": 10,
                "tags": ["aws", "cloud"],
                "fingerprint": "fp-001",
            }
        ]
    }

    def test_normalize_returns_list_of_dicts(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert isinstance(rows[0], dict)

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        for row in rows:
            assert row["profile"] == _PROFILE

    def test_normalize_correct_field_names(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        row = rows[0]
        assert "file_path" in row
        assert "rule_id" in row
        assert "line_number" in row

    def test_normalize_type_flags_present(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_secret_true(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        assert rows[0]["type_secret"] is True

    def test_normalize_other_type_flags_false(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS - {"type_secret"}:
            assert row[key] is False, f"{key} should be False for gitleaks"

    def test_normalize_empty_secrets(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", {"secrets": []}), _PROFILE)
        assert rows == []

    def test_render_non_empty_string(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_rule_id(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "aws-access-token" in text

    def test_render_contains_file_path(self) -> None:
        handler = GitleaksChunkBuilder()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "config/aws.py" in text


# ---------------------------------------------------------------------------
# Nmap
# ---------------------------------------------------------------------------


class TestNmapHandler:
    _PARSED_TWO_PORTS: dict = {
        "hosts": [
            {
                "ip_address": "192.168.1.1",
                "hostname": "router",
                "state": "up",
                "ports": [
                    {"port": 22, "transport": "tcp", "state": "open", "service": "ssh"},
                    {
                        "port": 80,
                        "transport": "tcp",
                        "state": "open",
                        "service": "http",
                    },
                    {
                        "port": 443,
                        "transport": "tcp",
                        "state": "closed",
                        "service": "https",
                    },
                ],
            }
        ]
    }
    _PARSED_ONE_PORT: dict = {
        "hosts": [
            {
                "ip_address": "10.0.0.1",
                "hostname": "",
                "state": "up",
                "ports": [
                    {"port": 22, "transport": "tcp", "state": "open", "service": "ssh"},
                ],
            }
        ]
    }

    def test_normalize_one_dict_per_open_port(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_TWO_PORTS), _PROFILE)
        assert len(rows) == 2

    def test_normalize_no_host_level_rows(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_TWO_PORTS), _PROFILE)
        for row in rows:
            assert "port" in row, "Every row must be a port-level row"

    def test_normalize_closed_port_excluded(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_TWO_PORTS), _PROFILE)
        ports = {row["port"] for row in rows}
        assert 443 not in ports

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        for row in rows:
            assert row["profile"] == _PROFILE

    def test_normalize_field_names(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        row = rows[0]
        assert "ip_address" in row
        assert "port" in row
        assert "service" in row

    def test_normalize_finding_type_exposure(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        assert rows[0]["finding_type"] == '["exposure"]'

    def test_normalize_type_exposure_true(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        assert rows[0]["type_exposure"] is True

    def test_normalize_type_flags_present(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_no_hosts_returns_empty(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", {"hosts": []}), _PROFILE)
        assert rows == []

    def test_render_non_empty_string(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_ip_address(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        text = handler.render(rows[0])
        assert "10.0.0.1" in text

    def test_render_contains_port(self) -> None:
        handler = NmapChunkBuilder()
        rows = handler.normalize(_make_result("nmap", self._PARSED_ONE_PORT), _PROFILE)
        text = handler.render(rows[0])
        assert "22" in text


# ---------------------------------------------------------------------------
# Semgrep
# ---------------------------------------------------------------------------


class TestSemgrepHandler:
    _PARSED: dict = {
        "findings": [
            {
                "rule_id": "python.lang.security.audit.hardcoded-password",
                "severity": "high",
                "message": "Hardcoded password detected",
                "file_path": "src/auth.py",
                "line_start": 42,
                "line_end": 42,
            }
        ]
    }

    def test_normalize_returns_list_of_dicts(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        assert rows[0]["profile"] == _PROFILE

    def test_normalize_correct_field_names(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        row = rows[0]
        assert "file_path" in row
        assert "rule_id" in row
        assert "line_start" in row

    def test_normalize_type_flags_present(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_vulnerability_and_weakness_true(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        assert rows[0]["type_vulnerability"] is True
        assert rows[0]["type_weakness"] is True

    def test_render_non_empty_string(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_rule_id(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "python.lang.security.audit.hardcoded-password" in text

    def test_render_contains_file_path(self) -> None:
        handler = SemgrepChunkBuilder()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "src/auth.py" in text


# ---------------------------------------------------------------------------
# ZAP
# ---------------------------------------------------------------------------


class TestZapHandler:
    _PARSED: dict = {
        "alerts": [
            {
                "alert_name": "SQL Injection",
                "risk": "high",
                "confidence": "confirmed",
                "url": "https://example.com/api/users",
                "method": "POST",
                "description": "SQL injection vulnerability detected",
                "solution": "Use parameterised queries",
            }
        ]
    }

    def test_normalize_returns_list_of_dicts(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        assert rows[0]["profile"] == _PROFILE

    def test_normalize_correct_field_names(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        row = rows[0]
        assert "url" in row
        assert "alert_name" in row
        assert "method" in row

    def test_normalize_type_flags_present(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_vulnerability_true(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        assert rows[0]["type_vulnerability"] is True

    def test_render_non_empty_string(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_alert_name(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "SQL Injection" in text

    def test_render_contains_url(self) -> None:
        handler = ZapChunkBuilder()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "example.com" in text


# ---------------------------------------------------------------------------
# SCA tools (pip-audit, npm-audit, composer-audit, osv-scanner)
# ---------------------------------------------------------------------------


_SCA_PARSED: dict = {
    "vulnerabilities": [
        {
            "package_name": "requests",
            "package_version": "2.27.0",
            "vulnerability_id": "CVE-2023-32681",
            "severity": "medium",
            "summary": "HTTP redirect handling issue",
            "affected_ecosystem": "PyPI",
        }
    ]
}


@pytest.mark.parametrize(
    "handler_cls, tool_name",
    [
        (PipAuditChunkBuilder, "pip-audit"),
        (NpmAuditChunkBuilder, "npm-audit"),
        (ComposerAuditChunkBuilder, "composer-audit"),
        (OsvScannerChunkBuilder, "osv-scanner"),
    ],
)
class TestScaHandlers:
    def test_normalize_returns_list_of_dicts(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert isinstance(rows[0], dict)

    def test_normalize_profile_in_every_dict(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        for row in rows:
            assert row["profile"] == _PROFILE

    def test_normalize_correct_field_names(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        row = rows[0]
        assert "package_name" in row
        assert "package_version" in row
        assert "vulnerability_id" in row
        assert "ecosystem" in row

    def test_normalize_type_flags_present(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_dependency_and_vulnerability_true(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        assert rows[0]["type_dependency"] is True
        assert rows[0]["type_vulnerability"] is True

    def test_normalize_empty_vulnerabilities(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(
            _make_result(tool_name, {"vulnerabilities": []}), _PROFILE
        )
        assert rows == []

    def test_render_non_empty_string(self, handler_cls: type, tool_name: str) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_package_name(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "requests" in text

    def test_render_contains_vulnerability_id(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "CVE-2023-32681" in text

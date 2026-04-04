"""Unit tests for ToolHandler normalize() and render() methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.rag.chunks.composer_audit import ComposerAuditHandler
from application.rag.chunks.gitleaks import GitleaksHandler
from application.rag.chunks.npm_audit import NpmAuditHandler
from application.rag.chunks.osv_scanner import OsvScannerHandler
from application.rag.chunks.pip_audit import PipAuditHandler
from application.rag.chunks.semgrep import SemgrepHandler
from application.rag.chunks.zap import ZapHandler
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
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert isinstance(rows[0], dict)

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        for row in rows:
            assert row["profile"] == _PROFILE

    def test_normalize_correct_field_names(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        row = rows[0]
        assert "file_path" in row
        assert "rule_id" in row
        assert "line_number" in row
        assert row["file_path"] == "config/aws.py"
        assert row["rule_id"] == "aws-access-token"
        assert row["line_number"] == 10

    def test_normalize_type_flags_present(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_secret_true(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        assert rows[0]["type_secret"] is True

    def test_normalize_other_type_flags_false(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS - {"type_secret"}:
            assert row[key] is False, f"{key} should be False for gitleaks"

    def test_normalize_empty_secrets(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", {"secrets": []}), _PROFILE)
        assert rows == []

    def test_render_non_empty_string(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_rule_id(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "aws-access-token" in text

    def test_render_contains_file_path(self) -> None:
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "config/aws.py" in text

    def test_normalize_multiple_secrets_returns_multiple_rows(self) -> None:
        """Multiple secrets in parsed_data produce one row each."""
        parsed = {
            "secrets": [
                {
                    "rule_id": "aws-access-token",
                    "description": "AWS key",
                    "file_path": "config/aws.py",
                    "line_number": 10,
                    "tags": [],
                    "fingerprint": "fp-001",
                },
                {
                    "rule_id": "github-token",
                    "description": "GitHub token",
                    "file_path": "config/github.py",
                    "line_number": 20,
                    "tags": [],
                    "fingerprint": "fp-002",
                },
                {
                    "rule_id": "generic-api-key",
                    "description": "Generic API key",
                    "file_path": "src/api.py",
                    "line_number": 5,
                    "tags": [],
                    "fingerprint": "fp-003",
                },
            ]
        }
        handler = GitleaksHandler()
        rows = handler.normalize(_make_result("gitleaks", parsed), _PROFILE)
        assert len(rows) == 3
        rule_ids = {r["rule_id"] for r in rows}
        assert "aws-access-token" in rule_ids
        assert "github-token" in rule_ids
        assert "generic-api-key" in rule_ids


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
                "cwe": "CWE-798",
            }
        ]
    }

    def test_normalize_returns_list_of_dicts(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        assert rows[0]["profile"] == _PROFILE

    def test_normalize_correct_field_names(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        row = rows[0]
        assert "file_path" in row
        assert "rule_id" in row
        assert "line_start" in row
        assert row["file_path"] == "src/auth.py"
        assert row["rule_id"] == "python.lang.security.audit.hardcoded-password"
        assert row["line_start"] == 42

    def test_normalize_type_flags_present(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_vulnerability_and_weakness_true(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        assert rows[0]["type_vulnerability"] is True
        assert rows[0]["type_weakness"] is True

    def test_render_non_empty_string(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_rule_id(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "python.lang.security.audit.hardcoded-password" in text

    def test_render_contains_file_path(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "src/auth.py" in text

    def test_render_contains_description(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "Hardcoded password detected" in text

    def test_render_contains_cwe(self) -> None:
        handler = SemgrepHandler()
        rows = handler.normalize(_make_result("semgrep", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "CWE-798" in text


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
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        assert isinstance(rows, list)
        assert len(rows) == 1

    def test_normalize_profile_in_every_dict(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        assert rows[0]["profile"] == _PROFILE

    def test_normalize_correct_field_names(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        row = rows[0]
        assert "url" in row
        assert "alert_name" in row
        assert "method" in row
        assert row["url"] == "https://example.com/api/users"
        assert row["alert_name"] == "SQL Injection"
        assert row["method"] == "POST"

    def test_normalize_type_flags_present(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        row = rows[0]
        for key in _TYPE_FLAG_KEYS:
            assert key in row

    def test_normalize_type_vulnerability_true(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        assert rows[0]["type_vulnerability"] is True

    def test_render_non_empty_string(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert isinstance(text, str)
        assert len(text) > 0

    def test_render_contains_alert_name(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "SQL Injection" in text

    def test_render_contains_url(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "example.com" in text

    def test_render_contains_description(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "SQL injection vulnerability detected" in text

    def test_render_contains_severity(self) -> None:
        handler = ZapHandler()
        rows = handler.normalize(_make_result("zap", self._PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "high" in text


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
        (PipAuditHandler, "pip-audit"),
        (NpmAuditHandler, "npm-audit"),
        (ComposerAuditHandler, "composer-audit"),
        (OsvScannerHandler, "osv-scanner"),
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

    def test_normalize_multiple_vulns_returns_multiple_rows(
        self, handler_cls: type, tool_name: str
    ) -> None:
        """Multiple vulnerabilities produce one row each with distinct IDs."""
        parsed: dict = {
            "vulnerabilities": [
                {
                    "package_name": "requests",
                    "package_version": "2.25.0",
                    "vulnerability_id": "CVE-2023-001",
                    "severity": "high",
                    "summary": "vuln 1",
                    "affected_ecosystem": "PyPI",
                },
                {
                    "package_name": "flask",
                    "package_version": "1.0.0",
                    "vulnerability_id": "CVE-2023-002",
                    "severity": "medium",
                    "summary": "vuln 2",
                    "affected_ecosystem": "PyPI",
                },
                {
                    "package_name": "django",
                    "package_version": "2.2.0",
                    "vulnerability_id": "CVE-2023-003",
                    "severity": "critical",
                    "summary": "vuln 3",
                    "affected_ecosystem": "PyPI",
                },
            ]
        }
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, parsed), _PROFILE)
        assert len(rows) == 3
        vuln_ids = {r["vulnerability_id"] for r in rows}
        assert vuln_ids == {"CVE-2023-001", "CVE-2023-002", "CVE-2023-003"}

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

    def test_render_contains_description(
        self, handler_cls: type, tool_name: str
    ) -> None:
        handler = handler_cls()
        rows = handler.normalize(_make_result(tool_name, _SCA_PARSED), _PROFILE)
        text = handler.render(rows[0])
        assert "HTTP redirect handling issue" in text


class TestOsvScannerRenderCwe:
    """osv-scanner-specific render() test for cwe_ids field."""

    _PARSED_WITH_CWE: dict = {
        "vulnerabilities": [
            {
                "package_name": "pyyaml",
                "package_version": "5.3.1",
                "vulnerability_id": "CVE-2020-14343",
                "severity": "critical",
                "summary": "Arbitrary code execution via YAML deserialisation",
                "affected_ecosystem": "PyPI",
                "cwe_ids": ["CWE-502"],
            }
        ]
    }

    def test_render_contains_cwe_ids(self) -> None:
        handler = OsvScannerHandler()
        rows = handler.normalize(
            _make_result("osv-scanner", self._PARSED_WITH_CWE), _PROFILE
        )
        text = handler.render(rows[0])
        assert "CWE-502" in text

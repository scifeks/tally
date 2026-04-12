"""Unit tests for fingerprint_key() methods on ToolHandler classes."""

from __future__ import annotations

from infrastructure.tools.parsers.gitleaks import GitleaksHandler
from infrastructure.tools.parsers.pip_audit import PipAuditHandler
from infrastructure.tools.parsers.semgrep import SemgrepHandler
from infrastructure.tools.parsers.zap import ZapHandler


class TestGitleaksFingerprintKey:
    def test_exact(self) -> None:
        result = GitleaksHandler().fingerprint_key(
            {"rule_id": "aws-key", "file_path": "/src/main.py", "line_number": 42}
        )
        assert result == "gitleaks|aws-key|/src/main.py|42"

    def test_missing_fields_produce_empty_segments(self) -> None:
        result = GitleaksHandler().fingerprint_key({})
        assert result == "gitleaks|||"

    def test_distinct_inputs_produce_distinct_keys(self) -> None:
        h = GitleaksHandler()
        key_a = h.fingerprint_key(
            {"rule_id": "A", "file_path": "/a.py", "line_number": 1}
        )
        key_b = h.fingerprint_key(
            {"rule_id": "B", "file_path": "/a.py", "line_number": 1}
        )
        assert key_a != key_b


class TestSemgrepFingerprintKey:
    def test_exact(self) -> None:
        result = SemgrepHandler().fingerprint_key(
            {"rule_id": "sqli", "file_path": "/app/db.py", "line_start": 10}
        )
        assert result == "semgrep|sqli|/app/db.py|10"


class TestZapFingerprintKey:
    def test_exact(self) -> None:
        result = ZapHandler().fingerprint_key(
            {"url": "https://example.com/api", "method": "GET", "alert_name": "XSS"}
        )
        assert result == "zap|https://example.com/api|GET|XSS"


class TestScaFingerprintKeys:
    def test_pip_audit_key(self) -> None:
        result = PipAuditHandler().fingerprint_key(
            {
                "package_name": "requests",
                "vulnerability_id": "CVE-2023-1234",
                "ecosystem": "PyPI",
            }
        )
        assert result == "pip-audit|requests|CVE-2023-1234|PyPI"

    def test_key_uses_tool_field_in_dict(self) -> None:
        result = PipAuditHandler().fingerprint_key(
            {
                "tool": "osv-scanner",
                "package_name": "flask",
                "vulnerability_id": "CVE-2024-9999",
                "ecosystem": "PyPI",
            }
        )
        assert result.startswith("osv-scanner|")

    def test_all_sca_tools_registered(self) -> None:
        from application.rag.ingestor import ToolHandlerFactory

        expected = {
            "gitleaks",
            "semgrep",
            "zap",
            "pip-audit",
            "npm-audit",
            "composer-audit",
            "osv-scanner",
            "noir",
        }
        for tool in expected:
            handler = ToolHandlerFactory.load(tool)
            assert handler is not None, f"No handler found for {tool!r}"

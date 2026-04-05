"""Unit tests for fingerprint key functions (infrastructure.tools.fingerprints)."""

from __future__ import annotations

from infrastructure.tools.fingerprints import (
    FINGERPRINT_REGISTRY,
    _gitleaks_fingerprint_key,
    _noir_fingerprint_key,
    _sca_fingerprint_key,
    _semgrep_fingerprint_key,
    _zap_fingerprint_key,
)


class TestFingerprintKeys:
    def test_gitleaks_key_exact(self) -> None:
        result = _gitleaks_fingerprint_key(
            {
                "repo": "myrepo",
                "rule_id": "aws-key",
                "file_path": "/src/main.py",
                "line_number": 42,
            }
        )
        assert result == "gitleaks|myrepo|aws-key|/src/main.py|42"

    def test_semgrep_key_exact(self) -> None:
        result = _semgrep_fingerprint_key(
            {
                "repo": "myrepo",
                "rule_id": "sqli",
                "file_path": "/app/db.py",
                "line_start": 10,
            }
        )
        assert result == "semgrep|myrepo|sqli|/app/db.py|10"

    def test_zap_key_exact(self) -> None:
        result = _zap_fingerprint_key(
            {
                "repo": "myrepo",
                "url": "https://example.com/api",
                "method": "GET",
                "alert_name": "XSS",
            }
        )
        assert result == "zap|myrepo|https://example.com/api|GET|XSS"

    def test_sca_key_uses_tool_name_param(self) -> None:
        result = _sca_fingerprint_key(
            "pip-audit",
            {
                "repo": "myrepo",
                "package_name": "requests",
                "vulnerability_id": "CVE-2023-1234",
                "ecosystem": "PyPI",
            },
        )
        assert result == "pip-audit|myrepo|requests|CVE-2023-1234|PyPI"

    def test_sca_key_prefers_tool_field_in_dict(self) -> None:
        result = _sca_fingerprint_key(
            "pip-audit",
            {
                "tool": "osv-scanner",
                "repo": "myrepo",
                "package_name": "flask",
                "vulnerability_id": "CVE-2024-9999",
                "ecosystem": "PyPI",
            },
        )
        assert result.startswith("osv-scanner|")

    def test_noir_key_exact(self) -> None:
        result = _noir_fingerprint_key(
            {"repo": "myrepo", "method": "POST", "url": "/api/login"}
        )
        assert result == "noir|myrepo|POST|/api/login"

    def test_distinct_inputs_produce_distinct_keys(self) -> None:
        key_a = _gitleaks_fingerprint_key(
            {"rule_id": "A", "file_path": "/a.py", "line_number": 1}
        )
        key_b = _gitleaks_fingerprint_key(
            {"rule_id": "B", "file_path": "/a.py", "line_number": 1}
        )
        assert key_a != key_b

    def test_missing_fields_produce_empty_segments(self) -> None:
        result = _gitleaks_fingerprint_key({})
        assert result == "gitleaks||||"

    def test_registry_contains_all_expected_tools(self) -> None:
        assert set(FINGERPRINT_REGISTRY.keys()) == {
            "gitleaks",
            "semgrep",
            "zap",
            "pip-audit",
            "npm-audit",
            "composer-audit",
            "osv-scanner",
            "noir",
        }

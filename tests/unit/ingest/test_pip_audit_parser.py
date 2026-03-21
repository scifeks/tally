"""Unit tests for the pip-audit JSON parser."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.parsers.pip_audit_parser import (
    parse_pip_audit_json,
    parse_pip_audit_json_string,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


def _parse_fixture(filename: str) -> dict:
    return parse_pip_audit_json(_FIXTURES / filename)


class TestPipAuditParser:
    def test_parse_json_string_basic(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "django",
                        "version": "3.2.0",
                        "vulns": [
                            {
                                "id": "PYSEC-2024-1",
                                "description": "SQL injection in ORM",
                                "fix_versions": ["3.2.20"],
                                "severity": "CRITICAL",
                            }
                        ],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert "vulnerabilities" in parsed
        assert len(parsed["vulnerabilities"]) == 1
        vuln = parsed["vulnerabilities"][0]
        assert vuln["vulnerability_id"] == "PYSEC-2024-1"
        assert vuln["package_name"] == "django"
        assert vuln["package_version"] == "3.2.0"
        assert vuln["severity"] == "critical"
        assert vuln["fixed_version"] == "3.2.20"

    def test_parse_error_returns_error_key(self) -> None:
        result = parse_pip_audit_json_string("not json {{{{")
        assert "error" in result

    def test_severity_defaults_to_low(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [{"id": "X", "description": "", "fix_versions": []}],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["severity"] == "low"

    def test_severity_map_critical(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [
                            {
                                "id": "X",
                                "description": "",
                                "fix_versions": [],
                                "severity": "CRITICAL",
                            }
                        ],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["severity"] == "critical"

    def test_fixed_version_first_of_list(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [
                            {
                                "id": "X",
                                "description": "",
                                "fix_versions": ["1.1", "2.0"],
                            }
                        ],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["fixed_version"] == "1.1"

    def test_fixed_version_none_when_empty(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [{"id": "X", "description": "", "fix_versions": []}],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["fixed_version"] is None

    def test_cvss_score_always_none(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        for vuln in parsed["vulnerabilities"]:
            assert vuln["cvss_score"] is None, (
                f"cvss_score must always be None, got {vuln['cvss_score']!r}"
            )

    def test_source_file_always_empty_string(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        for vuln in parsed["vulnerabilities"]:
            assert vuln["source_file"] == "", (
                f"source_file must always be '', got {vuln['source_file']!r}"
            )

    def test_ecosystem_always_pypi(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        for vuln in parsed["vulnerabilities"]:
            assert vuln["affected_ecosystem"] == "PyPI"

    def test_summary_counts(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        summary = parsed["summary"]
        assert summary["total_vulnerabilities"] == 2
        assert summary["packages_scanned"] == 3
        assert summary["ecosystems"] == ["PyPI"]

    def test_no_vulns_produces_empty_list(self) -> None:
        parsed = _parse_fixture("pip_audit_no_vulns.json")
        assert parsed["vulnerabilities"] == []
        assert parsed["summary"]["total_vulnerabilities"] == 0

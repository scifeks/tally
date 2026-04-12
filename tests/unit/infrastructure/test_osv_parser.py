"""Unit tests for the OSV-Scanner JSON parser
(infrastructure.tools.parsers.osv_scanner)."""

from __future__ import annotations

import json

from infrastructure.tools.parsers.osv_scanner import parse_osv_json_string


def _wrap_vuln(vuln: dict, pkg_name: str = "requests", ecosystem: str = "PyPI") -> dict:
    """Build a minimal OSV results structure wrapping a single vulnerability dict."""
    return {
        "results": [
            {
                "source": {"path": "/app/requirements.txt", "type": "lockfile"},
                "packages": [
                    {
                        "package": {
                            "name": pkg_name,
                            "version": "1.0.0",
                            "ecosystem": ecosystem,
                        },
                        "vulnerabilities": [vuln],
                    }
                ],
            }
        ]
    }


class TestOsvParser:
    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_osv_json_string("not json")
        assert "error" in result

    def test_empty_results_returns_empty_vulnerabilities(self) -> None:
        result = parse_osv_json_string('{"results": []}')
        assert result["vulnerabilities"] == []
        assert result["summary"]["total_vulnerabilities"] == 0

    def test_success_path_field_mapping(self) -> None:
        data = _wrap_vuln(
            {
                "id": "GHSA-xxx",
                "summary": "A bug",
                "database_specific": {"severity": "HIGH"},
            }
        )
        result = parse_osv_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["package_name"] == "requests"
        assert vuln["vulnerability_id"] == "GHSA-xxx"

    def test_database_specific_severity_high_maps_correctly(self) -> None:
        data = _wrap_vuln({"id": "GHSA-yyy", "database_specific": {"severity": "HIGH"}})
        result = parse_osv_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["severity"] == "high"

    def test_missing_severity_field_defaults_to_low(self) -> None:
        data = _wrap_vuln({"id": "GHSA-zzz", "database_specific": {}})
        result = parse_osv_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["severity"] == "low"

    def test_cvss_score_9_and_above_is_critical(self) -> None:
        data = _wrap_vuln(
            {
                "id": "GHSA-crit",
                "severity": [{"type": "CVSS_V3", "score": "9.8"}],
                "database_specific": {},
            }
        )
        result = parse_osv_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["severity"] == "critical"

    def test_cvss_score_7_to_9_is_high(self) -> None:
        data = _wrap_vuln(
            {
                "id": "GHSA-high",
                "severity": [{"type": "CVSS_V3", "score": "7.5"}],
                "database_specific": {},
            }
        )
        result = parse_osv_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["severity"] == "high"

    def test_cvss_score_4_to_7_is_medium(self) -> None:
        data = _wrap_vuln(
            {
                "id": "GHSA-med",
                "severity": [{"type": "CVSS_V3", "score": "5.0"}],
                "database_specific": {},
            }
        )
        result = parse_osv_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["severity"] == "medium"

    def test_summary_ecosystems_are_sorted(self) -> None:
        data = {
            "results": [
                {
                    "source": {"path": "/app/go.sum", "type": "lockfile"},
                    "packages": [
                        {
                            "package": {
                                "name": "pkg-a",
                                "version": "1.0",
                                "ecosystem": "PyPI",
                            },
                            "vulnerabilities": [{"id": "A", "database_specific": {}}],
                        },
                        {
                            "package": {
                                "name": "pkg-b",
                                "version": "1.0",
                                "ecosystem": "Go",
                            },
                            "vulnerabilities": [{"id": "B", "database_specific": {}}],
                        },
                    ],
                }
            ]
        }
        result = parse_osv_json_string(json.dumps(data))
        assert result["summary"]["ecosystems"] == ["Go", "PyPI"]

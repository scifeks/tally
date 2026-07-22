"""Unit tests for the Retire.js JSON parser."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.parsers.retire import (
    RetireHandler,
    parse_retire_json,
    parse_retire_json_string,
)


def _wrap_vuln(vuln: dict, component: str = "jquery", version: str = "1.6.2") -> list:
    """Build a minimal Retire.js results structure wrapping a single vuln."""
    return [
        {
            "file": "js/jquery.min.js",
            "results": [
                {
                    "component": component,
                    "version": version,
                    "detection": "filecontent",
                    "vulnerabilities": [vuln],
                }
            ],
        }
    ]


class TestParseRetireJsonString:
    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_retire_json_string("not json")
        assert "error" in result

    def test_empty_string_returns_error_key(self) -> None:
        result = parse_retire_json_string("")
        assert "error" in result

    def test_empty_array_returns_empty_vulnerabilities(self) -> None:
        result = parse_retire_json_string("[]")
        assert result["vulnerabilities"] == []
        assert result["summary"]["total_vulnerabilities"] == 0

    def test_component_maps_to_package_name(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "medium",
                "identifiers": {
                    "CVE": ["CVE-2012-6708"],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["package_name"] == "jquery"

    def test_version_maps_to_package_version(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "medium",
                "identifiers": {
                    "CVE": ["CVE-2012-6708"],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            },
            version="2.0.1",
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["package_version"] == "2.0.1"

    def test_cve_first_entry_is_vulnerability_id(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "high",
                "identifiers": {
                    "CVE": ["CVE-2012-6708"],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["vulnerability_id"] == "CVE-2012-6708"

    def test_multiple_cves_first_is_id_rest_are_aliases(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "high",
                "identifiers": {
                    "CVE": ["CVE-2012-6708", "CVE-2013-1234"],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["vulnerability_id"] == "CVE-2012-6708"
        assert vuln["aliases"] == ["CVE-2013-1234"]

    def test_no_cve_uses_empty_id(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "medium",
                "identifiers": {
                    "CVE": [],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["vulnerability_id"] == ""

    def test_severity_passed_through(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "critical",
                "identifiers": {
                    "CVE": ["CVE-2012-6708"],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["severity"] == "critical"

    def test_ecosystem_is_npm(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "medium",
                "identifiers": {
                    "CVE": ["CVE-2012-6708"],
                    "summary": "A bug",
                },
                "info": ["https://example.com"],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["affected_ecosystem"] == "npm"

    def test_file_path_maps_to_source_file(self) -> None:
        data = [
            {
                "file": "js/app.js",
                "results": [
                    {
                        "component": "jquery",
                        "version": "1.0",
                        "detection": "filecontent",
                        "vulnerabilities": [
                            {
                                "severity": "low",
                                "identifiers": {
                                    "CVE": ["CVE-2012-6708"],
                                    "summary": "A bug",
                                },
                                "info": ["https://example.com"],
                            }
                        ],
                    }
                ],
            }
        ]
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["source_file"] == "js/app.js"

    def test_info_list_becomes_references(self) -> None:
        data = _wrap_vuln(
            {
                "severity": "medium",
                "identifiers": {
                    "CVE": ["CVE-2012-6708"],
                    "summary": "A bug",
                },
                "info": [
                    "https://example.com/1",
                    "https://example.com/2",
                ],
            }
        )
        result = parse_retire_json_string(json.dumps(data))
        vuln = result["vulnerabilities"][0]
        assert vuln["references"] == [
            "https://example.com/1",
            "https://example.com/2",
        ]

    def test_summary_by_severity_populated(self) -> None:
        data = [
            {
                "file": "js/jquery.min.js",
                "results": [
                    {
                        "component": "jquery",
                        "version": "1.0",
                        "detection": "filecontent",
                        "vulnerabilities": [
                            {
                                "severity": "high",
                                "identifiers": {
                                    "CVE": ["CVE-1"],
                                    "summary": "Bug 1",
                                },
                                "info": [],
                            },
                            {
                                "severity": "medium",
                                "identifiers": {
                                    "CVE": ["CVE-2"],
                                    "summary": "Bug 2",
                                },
                                "info": [],
                            },
                            {
                                "severity": "high",
                                "identifiers": {
                                    "CVE": ["CVE-3"],
                                    "summary": "Bug 3",
                                },
                                "info": [],
                            },
                        ],
                    }
                ],
            }
        ]
        result = parse_retire_json_string(json.dumps(data))
        assert result["summary"]["by_severity"] == {"high": 2, "medium": 1}

    def test_multiple_components_per_file_counted(self) -> None:
        data = [
            {
                "file": "js/app.js",
                "results": [
                    {
                        "component": "jquery",
                        "version": "1.0",
                        "detection": "filecontent",
                        "vulnerabilities": [
                            {
                                "severity": "low",
                                "identifiers": {
                                    "CVE": ["CVE-1"],
                                    "summary": "Bug 1",
                                },
                                "info": [],
                            },
                            {
                                "severity": "low",
                                "identifiers": {
                                    "CVE": ["CVE-2"],
                                    "summary": "Bug 2",
                                },
                                "info": [],
                            },
                        ],
                    },
                    {
                        "component": "bootstrap",
                        "version": "3.0",
                        "detection": "filecontent",
                        "vulnerabilities": [
                            {
                                "severity": "high",
                                "identifiers": {
                                    "CVE": ["CVE-3"],
                                    "summary": "Bug 3",
                                },
                                "info": [],
                            }
                        ],
                    },
                ],
            }
        ]
        result = parse_retire_json_string(json.dumps(data))
        assert result["summary"]["total_vulnerabilities"] == 3


class TestParseRetireJson:
    def test_fixture_file_parses(self) -> None:
        fixture_path = (
            Path(__file__).parent.parent.parent
            / "fixtures"
            / "ingest"
            / "retire_output.json"
        )
        result = parse_retire_json(fixture_path)
        vulnerabilities = result["vulnerabilities"]
        assert len(vulnerabilities) == 3

    def test_fixture_contains_jquery_and_bootstrap(self) -> None:
        fixture_path = (
            Path(__file__).parent.parent.parent
            / "fixtures"
            / "ingest"
            / "retire_output.json"
        )
        result = parse_retire_json(fixture_path)
        vulnerabilities = result["vulnerabilities"]
        pkg_names = {v["package_name"] for v in vulnerabilities}
        assert pkg_names == {"jquery", "bootstrap"}

    def test_missing_file_returns_error(self) -> None:
        result = parse_retire_json(Path("/nonexistent/file.json"))
        assert "error" in result


class TestRetireHandler:
    def test_tool_name_is_retire(self) -> None:
        handler = RetireHandler()
        assert handler.tool_name == "retire"

    def test_domain_is_code(self) -> None:
        handler = RetireHandler()
        assert handler.domain == "code"

    def test_segment_is_sca(self) -> None:
        handler = RetireHandler()
        assert handler.segment == "sca"

    def test_fingerprint_key_is_stable(self) -> None:
        handler = RetireHandler()
        finding = {
            "tool": "retire",
            "package_name": "jquery",
            "vulnerability_id": "CVE-2012-6708",
            "ecosystem": "npm",
        }
        key1 = handler.fingerprint_key(finding)
        key2 = handler.fingerprint_key(finding)
        assert key1 == key2

    def test_fingerprint_key_contains_tool_package_vuln_id(self) -> None:
        handler = RetireHandler()
        finding = {
            "tool": "retire",
            "package_name": "jquery",
            "vulnerability_id": "CVE-2012-6708",
            "ecosystem": "npm",
        }
        key = handler.fingerprint_key(finding)
        assert "retire" in key
        assert "jquery" in key
        assert "CVE-2012-6708" in key

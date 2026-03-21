"""Unit tests for the npm audit JSON parser
(infrastructure.tools.parsers.npm_audit_parser)."""

from __future__ import annotations

import json

from infrastructure.tools.parsers.npm_audit_parser import parse_npm_audit_json_string


def _v2_data(vulns: dict) -> dict:
    return {"auditReportVersion": 2, "vulnerabilities": vulns}


def _v2_vuln(severity: str = "high", fix_available: bool | dict = False) -> dict:
    return {
        "severity": severity,
        "via": [{"title": "A vuln", "url": "https://npmjs.com/advisories/1"}],
        "range": ">=4.0.0 <4.17.21",
        "fixAvailable": fix_available,
    }


class TestNpmAuditParser:
    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_npm_audit_json_string("not json")
        assert "error" in result

    def test_empty_vulnerabilities_v2(self) -> None:
        result = parse_npm_audit_json_string(
            json.dumps({"auditReportVersion": 2, "vulnerabilities": {}})
        )
        assert result["vulnerabilities"] == []

    def test_v2_moderate_severity_maps_to_medium(self) -> None:
        data = _v2_data({"lodash": _v2_vuln("moderate")})
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["severity"] == "medium"

    def test_v2_ecosystem_is_npm(self) -> None:
        data = _v2_data({"lodash": _v2_vuln("high")})
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["affected_ecosystem"] == "npm"

    def test_v2_fix_available_dict_extracts_version(self) -> None:
        fix = {"name": "lodash", "version": "4.17.21", "isSemVerMajor": False}
        data = _v2_data({"lodash": _v2_vuln("high", fix)})
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["fixed_version"] == "4.17.21"

    def test_v2_fix_available_true_sets_fixed_version_none(self) -> None:
        data = _v2_data({"lodash": _v2_vuln("high", True)})
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["fixed_version"] is None

    def test_v1_empty_advisories(self) -> None:
        result = parse_npm_audit_json_string('{"advisories": {}}')
        assert result["vulnerabilities"] == []

    def test_v1_success_path_package_name(self) -> None:
        data = {
            "advisories": {
                "1234": {
                    "module_name": "lodash",
                    "severity": "high",
                    "cves": [],
                    "title": "Prototype pollution",
                    "vulnerable_versions": ">=0.0.0 <4.17.21",
                    "patched_versions": ">=4.17.21",
                }
            }
        }
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["package_name"] == "lodash"
        assert result["vulnerabilities"][0]["severity"] == "high"

    def test_v1_cve_used_as_vulnerability_id(self) -> None:
        data = {
            "advisories": {
                "1234": {
                    "module_name": "lodash",
                    "severity": "high",
                    "cves": ["CVE-2020-1234"],
                    "title": "Prototype pollution",
                    "vulnerable_versions": ">=0.0.0 <4.17.21",
                    "patched_versions": ">=4.17.21",
                }
            }
        }
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["vulnerability_id"] == "CVE-2020-1234"

    def test_v1_advisory_id_fallback_when_no_cve(self) -> None:
        data = {
            "advisories": {
                "5678": {
                    "module_name": "express",
                    "severity": "medium",
                    "cves": [],
                    "title": "Open redirect",
                    "vulnerable_versions": "<4.16.0",
                    "patched_versions": ">=4.16.0",
                }
            }
        }
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["vulnerability_id"] == "npm-advisory-5678"

    def test_summary_total_and_ecosystems(self) -> None:
        data = _v2_data(
            {
                "lodash": _v2_vuln("high"),
                "express": _v2_vuln("medium"),
            }
        )
        result = parse_npm_audit_json_string(json.dumps(data))
        assert result["summary"]["total_vulnerabilities"] == 2
        assert result["summary"]["ecosystems"] == ["npm"]

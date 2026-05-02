"""Unit tests for the composer audit JSON parser."""

from __future__ import annotations

import json

from infrastructure.tools.parsers.composer_audit import (
    parse_composer_audit_json_string,
)


def _one_advisory(
    pkg: str = "vendor/pkg",
    cve: str = "CVE-2023-9999",
    advisory_id: str = "PKSA-aaa",
) -> dict:
    return {
        "advisories": {
            pkg: [
                {
                    "cve": cve,
                    "advisoryId": advisory_id,
                    "title": "SQL injection",
                    "affectedVersions": ">=1.0.0,<1.2.0",
                    "link": "https://packagist.org/",
                }
            ]
        }
    }


class TestComposerAuditParser:
    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_composer_audit_json_string("not json")
        assert "error" in result

    def test_empty_advisories_returns_empty_vulnerabilities(self) -> None:
        result = parse_composer_audit_json_string('{"advisories": {}}')
        assert result["vulnerabilities"] == []

    def test_all_findings_have_severity_low(self) -> None:
        result = parse_composer_audit_json_string(json.dumps(_one_advisory()))
        for v in result["vulnerabilities"]:
            assert v["severity"] == "low"

    def test_success_path_cve_preferred_over_advisory_id(self) -> None:
        result = parse_composer_audit_json_string(json.dumps(_one_advisory()))
        assert result["vulnerabilities"][0]["vulnerability_id"] == "CVE-2023-9999"

    def test_advisory_id_used_when_cve_empty(self) -> None:
        data = _one_advisory(cve="", advisory_id="PKSA-bbb")
        result = parse_composer_audit_json_string(json.dumps(data))
        assert result["vulnerabilities"][0]["vulnerability_id"] == "PKSA-bbb"

    def test_success_path_package_name(self) -> None:
        result = parse_composer_audit_json_string(json.dumps(_one_advisory()))
        assert result["vulnerabilities"][0]["package_name"] == "vendor/pkg"

    def test_ecosystem_is_packagist(self) -> None:
        result = parse_composer_audit_json_string(json.dumps(_one_advisory()))
        assert result["vulnerabilities"][0]["affected_ecosystem"] == "Packagist"

    def test_summary_structure(self) -> None:
        result = parse_composer_audit_json_string(json.dumps(_one_advisory()))
        assert result["summary"]["ecosystems"] == ["Packagist"]
        assert result["summary"]["total_vulnerabilities"] == 1

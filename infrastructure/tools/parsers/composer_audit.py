"""Parser and handler for composer audit JSON output."""

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from ._sca_shared import (
    _SCA_COMMON_ENRICHMENT_FIELDS,
    _build_sca_normalize,
    _sca_fingerprint_key,
    _sca_render,
)

# composer audit does not expose severity; all findings default to "low"
_DEFAULT_SEVERITY = "low"


def parse_composer_audit_json(json_path: Path) -> dict[str, Any]:
    """Parse a composer audit JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_composer_audit_data(data)


def parse_composer_audit_json_string(json_string: str) -> dict[str, Any]:
    """Parse composer audit JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_composer_audit_data(data)


def _parse_composer_audit_data(data: dict[str, Any]) -> dict[str, Any]:
    vulnerabilities: list[dict[str, Any]] = []

    raw_advisories = data.get("advisories", {})
    if not isinstance(raw_advisories, dict):
        raw_advisories = {}
    seen: set[tuple[str, str]] = set()
    for pkg_name, advisories in raw_advisories.items():
        for advisory in advisories:
            cve = advisory.get("cve", "")
            advisory_id = advisory.get("advisoryId", "")
            vuln_id = cve or advisory_id

            key = (pkg_name, vuln_id)
            if key in seen:
                continue
            seen.add(key)

            vulnerabilities.append(
                {
                    "vulnerability_id": vuln_id,
                    "package_name": pkg_name,
                    "package_version": advisory.get("affectedVersions", ""),
                    "affected_ecosystem": "Packagist",
                    "severity": _DEFAULT_SEVERITY,
                    "summary": advisory.get("title", ""),
                    "fixed_version": None,
                    "cvss_score": None,
                    "source_file": "composer.json",
                }
            )

    by_severity: dict[str, int] = {}
    for v in vulnerabilities:
        sev = v["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "vulnerabilities": vulnerabilities,
        "summary": {
            "total_vulnerabilities": len(vulnerabilities),
            "by_severity": by_severity,
            "packages_scanned": 0,
            "ecosystems": ["Packagist"],
        },
    }


class ComposerAuditHandler:
    tool_name = "composer-audit"
    domain = "code"
    segment = "sca"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset()
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = _SCA_COMMON_ENRICHMENT_FIELDS
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }
    normalized_fields: list[str] = [
        "ecosystem",
        "file_path",
        "finding_type",
        "package_name",
        "severity",
        "vulnerability_id",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        return _build_sca_normalize(self, result, profile)

    def render(self, row: dict) -> str:
        return _sca_render(row)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("composer-audit", finding)

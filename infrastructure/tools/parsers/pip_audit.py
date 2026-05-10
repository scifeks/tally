"""Parser and handler for pip-audit JSON output."""

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

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}


def parse_pip_audit_json(json_path: Path) -> dict[str, Any]:
    """Parse a pip-audit JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_pip_audit_data(data)


def parse_pip_audit_json_string(json_string: str) -> dict[str, Any]:
    """Parse pip-audit JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_pip_audit_data(data)


def _parse_pip_audit_data(data: dict[str, Any]) -> dict[str, Any]:
    dependencies: list[dict[str, Any]] = data.get("dependencies", [])
    vulnerabilities: list[dict[str, Any]] = []

    for dep in dependencies:
        pkg_name = dep.get("name", "")
        pkg_version = dep.get("version", "")
        for vuln in dep.get("vulns", []):
            vulnerabilities.append(_parse_pip_vuln(vuln, pkg_name, pkg_version))

    by_severity: dict[str, int] = {}
    for v in vulnerabilities:
        sev = v["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "vulnerabilities": vulnerabilities,
        "summary": {
            "total_vulnerabilities": len(vulnerabilities),
            "by_severity": by_severity,
            "packages_scanned": len(dependencies),
            "ecosystems": ["PyPI"],
        },
    }


def _parse_pip_vuln(
    vuln: dict[str, Any], pkg_name: str, pkg_version: str
) -> dict[str, Any]:
    vuln_id = vuln.get("id", "")
    description = vuln.get("description", "")
    fix_versions: list[str] = vuln.get("fix_versions", [])
    fixed_version: str | None = fix_versions[0] if fix_versions else None

    # pip-audit severity is optional (added in newer versions); default to low
    raw_sev = vuln.get("severity", "").upper()
    severity = _SEVERITY_MAP.get(raw_sev, "low")

    return {
        "vulnerability_id": vuln_id,
        "package_name": pkg_name,
        "package_version": pkg_version,
        "affected_ecosystem": "PyPI",
        "severity": severity,
        "summary": description,
        "fixed_version": fixed_version,
        "cvss_score": None,
        "source_file": "",
    }


class PipAuditHandler:
    tool_name = "pip-audit"
    domain = "code"
    segment = "sca"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
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
        return _sca_fingerprint_key("pip-audit", finding)

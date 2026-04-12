"""Parser and handler for npm audit JSON output (v1 and v2 formats)."""

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

# npm severity → normalised label
_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "moderate": "medium",
    "medium": "medium",
    "low": "low",
    "info": "low",
}


# ---------------------------------------------------------------------------
# Parse functions (called by BaseNpmAuditTool.parse_output)
# ---------------------------------------------------------------------------


def parse_npm_audit_json(json_path: Path) -> dict[str, Any]:
    """Parse an npm audit JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_npm_audit_data(data)


def parse_npm_audit_json_string(json_string: str) -> dict[str, Any]:
    """Parse npm audit JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_npm_audit_data(data)


# ---------------------------------------------------------------------------
# Internal parse helpers
# ---------------------------------------------------------------------------


def _parse_npm_audit_data(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("auditReportVersion") == 2:
        return _parse_v2(data)
    return _parse_v1(data)


def _parse_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Parse npm audit v2 format (npm 7+)."""
    vulnerabilities: list[dict[str, Any]] = []

    for pkg_name, vuln_info in data.get("vulnerabilities", {}).items():
        severity = _SEVERITY_MAP.get(vuln_info.get("severity", "").lower(), "low")

        # Extract a human-readable summary and ID from the `via` list.
        # `via` entries are either advisory dicts or string references to
        # other packages in the vulnerability graph.
        vuln_id = ""
        summary = ""
        for via in vuln_info.get("via", []):
            if isinstance(via, dict):
                vuln_id = via.get("url", "") or via.get("name", "")
                summary = via.get("title", "")
                break
            if isinstance(via, str):
                vuln_id = via
                break

        # Affected version range
        affected_range = vuln_info.get("range", "")

        # Fixed version from fixAvailable (may be bool or dict)
        fix_available = vuln_info.get("fixAvailable")
        fixed_version: str | None = None
        if isinstance(fix_available, dict):
            fixed_version = fix_available.get("version")

        vulnerabilities.append(
            {
                "vulnerability_id": vuln_id or pkg_name,
                "package_name": pkg_name,
                "package_version": affected_range,
                "affected_ecosystem": "npm",
                "severity": severity,
                "summary": summary or f"Vulnerability in {pkg_name} ({affected_range})",
                "fixed_version": fixed_version,
                "cvss_score": None,
                "source_file": "package.json",
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
            "ecosystems": ["npm"],
        },
    }


def _parse_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Parse npm audit v1 format (npm 6)."""
    vulnerabilities: list[dict[str, Any]] = []

    for advisory_id, advisory in data.get("advisories", {}).items():
        severity = _SEVERITY_MAP.get(advisory.get("severity", "").lower(), "low")
        cves: list[str] = advisory.get("cves", [])
        vuln_id = cves[0] if cves else f"npm-advisory-{advisory_id}"
        pkg_name = advisory.get("module_name", "")
        patched = advisory.get("patched_versions", "")
        fixed_version: str | None = (
            patched if patched and patched not in ("<0.0.0", "*") else None
        )

        vulnerabilities.append(
            {
                "vulnerability_id": vuln_id,
                "package_name": pkg_name,
                "package_version": advisory.get("vulnerable_versions", ""),
                "affected_ecosystem": "npm",
                "severity": severity,
                "summary": advisory.get("title", ""),
                "fixed_version": fixed_version,
                "cvss_score": None,
                "source_file": "package.json",
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
            "ecosystems": ["npm"],
        },
    }


# ---------------------------------------------------------------------------
# Handler (normalize → SQLite rows, render → ChromaDB text)
# ---------------------------------------------------------------------------


class NpmAuditHandler:
    tool_name = "npm-audit"
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
        return _sca_fingerprint_key("npm-audit", finding)

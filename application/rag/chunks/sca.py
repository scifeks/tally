"""SCA shared helpers — used by the four dedicated SCA handler modules.

Handles: osv-scanner, pip-audit, npm-audit, composer-audit.
"""

import json
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

# ---------------------------------------------------------------------------
# Per-field enrichment specs
# ---------------------------------------------------------------------------

# pip-audit, npm-audit, composer-audit: limited metadata available.
_SCA_COMMON_ENRICHMENT_FIELDS: tuple[FieldEnrichmentSpec, ...] = (
    FieldEnrichmentSpec(
        "owasp_name",
        ("vulnerability_id", "description", "package_name"),
        PromptStrategy.DEDICATED,
    ),
    FieldEnrichmentSpec(
        "risk_type",
        ("vulnerability_id", "description"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "remediation",
        ("vulnerability_id", "description", "package_name", "fixed_version"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "confidence",
        ("description", "severity"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "title",
        ("vulnerability_id", "package_name", "package_version", "description"),
        PromptStrategy.GENERIC,
    ),
)

# osv-scanner: richer metadata including cwe_ids, aliases, details, cvss fields.
_SCA_OSV_ENRICHMENT_FIELDS: tuple[FieldEnrichmentSpec, ...] = (
    FieldEnrichmentSpec(
        "owasp_name",
        ("vulnerability_id", "description", "cwe_ids", "aliases", "details"),
        PromptStrategy.DEDICATED,
    ),
    FieldEnrichmentSpec(
        "risk_type",
        ("vulnerability_id", "description", "cwe_ids", "aliases"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "remediation",
        ("vulnerability_id", "description", "package_name", "fixed_version", "details"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "confidence",
        ("description", "severity", "cvss_score", "cvss_vector"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "title",
        (
            "vulnerability_id",
            "package_name",
            "package_version",
            "description",
            "aliases",
        ),
        PromptStrategy.GENERIC,
    ),
)


def _build_sca_normalize(builder: Any, result: ToolResult, profile: str) -> list[dict]:
    """Build normalized finding dicts for any SCA tool result."""
    tool = result.tool_name
    parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
    vulnerabilities: list[dict[str, Any]] = parsed.get("vulnerabilities", [])

    timestamp = result.timestamp
    source_file = _first_output_file(result.output_files)

    rows: list[dict] = []

    for vuln in vulnerabilities:
        pkg_name = vuln.get("package_name", "")
        pkg_version = vuln.get("package_version", "")
        vuln_id = vuln.get("vulnerability_id", "")
        aliases: list[str] = vuln.get("aliases") or []
        severity = vuln.get("severity", "low")
        summary = vuln.get("summary", "")
        ecosystem = vuln.get("affected_ecosystem", "")
        fixed_version = vuln.get("fixed_version")
        introduced_version = vuln.get("introduced_version")
        cvss_score = vuln.get("cvss_score")
        cvss_vector = vuln.get("cvss_vector", "")
        lockfile = vuln.get("source_file", "")
        source_type = vuln.get("source_type", "")
        details = vuln.get("details", "")
        published = vuln.get("published", "")
        modified = vuln.get("modified", "")
        references: list[str] = vuln.get("references") or []
        cwe_ids: list[str] = vuln.get("cwe_ids") or []

        row: dict[str, Any] = {
            "tool": tool,
            "profile": profile,
            "finding_type": json.dumps(["dependency"]),
            "severity": severity,
            "package_name": pkg_name,
            "package_version": pkg_version,
            "vulnerability_id": vuln_id,
            "ecosystem": ecosystem,
            "timestamp": timestamp,
            "source_file": source_file,
        }
        if summary:
            row["description"] = summary
        if aliases:
            row["aliases"] = ", ".join(aliases)
        if fixed_version:
            row["fixed_version"] = fixed_version
        if introduced_version:
            row["introduced_version"] = introduced_version
        if cvss_score is not None:
            row["cvss_score"] = cvss_score
        if cvss_vector:
            row["cvss_vector"] = cvss_vector
        if lockfile:
            row["lockfile"] = lockfile
        if source_type:
            row["source_type"] = source_type
        if details:
            row["details"] = details
        if published:
            row["published"] = published
        if modified:
            row["modified"] = modified
        if references:
            row["references"] = ", ".join(references)
        if cwe_ids:
            row["cwe_ids"] = ", ".join(cwe_ids)
        row.update(_shared_meta(builder, "dependency"))

        rows.append(row)

    return rows


def _sca_render(row: dict) -> str:
    tool = row.get("tool", "")
    pkg_name = row.get("package_name", "")
    pkg_version = row.get("package_version", "")
    vuln_id = row.get("vulnerability_id", "")
    severity = row.get("severity", "")
    return (
        f"[{tool}] Package: {pkg_name}@{pkg_version}"
        f" | Vuln: {vuln_id} | Severity: {severity}"
    )

"""SCA shared helpers for osv-scanner, pip-audit, npm-audit, composer-audit."""

import json
from typing import Any, cast

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

# Per-field enrichment specs

# pip-audit, npm-audit, composer-audit: limited metadata available.
_SCA_COMMON_ENRICHMENT_FIELDS: tuple[FieldEnrichmentSpec, ...] = (
    FieldEnrichmentSpec(
        "owasp_name",
        ("vulnerability_id", "description", "package_name"),
        PromptStrategy.DEDICATED,
    ),
    FieldEnrichmentSpec(
        "risk_type",
        ("vulnerability_id", "description", "cwe_description", "epss_score"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "remediation",
        ("vulnerability_id", "description", "package_name", "fixed_version"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "confidence",
        ("description", "severity", "epss_score"),
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
        (
            "vulnerability_id",
            "description",
            "cwe_ids",
            "cwe_description",
            "epss_score",
            "aliases",
        ),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "remediation",
        ("vulnerability_id", "description", "package_name", "fixed_version", "details"),
        PromptStrategy.GENERIC,
    ),
    FieldEnrichmentSpec(
        "confidence",
        ("description", "severity", "cvss_score", "cvss_vector", "epss_score"),
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
    parsed: dict[str, Any] = cast(dict[str, Any], result.parsed_data or {})
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
        baseline_title = summary or (
            f"{vuln_id} in {pkg_name}" if vuln_id and pkg_name else vuln_id or pkg_name
        )
        if baseline_title:
            row["title"] = baseline_title
        row.update(_shared_meta(builder, "dependency"))

        rows.append(row)

    return rows


def _sca_render(row: dict) -> str:
    tool = row.get("tool", "")
    parts = [
        f"Package: {row.get('package_name', '')}@{row.get('package_version', '')}",
        f"Vuln: {row.get('vulnerability_id', '')}",
        f"Severity: {row.get('severity', '')}",
    ]
    if row.get("description"):
        parts.append(f"Description: {row['description']}")
    if row.get("aliases"):
        parts.append(f"Aliases: {row['aliases']}")
    if row.get("cwe_ids"):
        parts.append(f"CWE: {row['cwe_ids']}")
    if row.get("cvss_score") is not None:
        parts.append(f"CVSS: {row['cvss_score']}")
    if row.get("fixed_version"):
        parts.append(f"Fixed in: {row['fixed_version']}")
    if row.get("details"):
        parts.append(f"Details: {row['details']}")
    if row.get("risk_type"):
        parts.append(f"Risk type: {row['risk_type']}")
    if row.get("title"):
        parts.append(f"Title: {row['title']}")
    if row.get("remediation"):
        parts.append(f"Remediation: {row['remediation']}")
    if row.get("owasp_name"):
        parts.append(f"OWASP category: {row['owasp_name']}")
    return f"[{tool}] " + " | ".join(parts)


def _sca_fingerprint_key(tool_name: str, finding: dict[str, Any]) -> str:
    tool = finding.get("tool") or tool_name
    return "|".join(
        [
            str(tool),
            str(finding.get("package_name", "")),
            str(finding.get("vulnerability_id", "")),
            str(finding.get("ecosystem", "")),
        ]
    )

"""SCA shared helpers — used by the four dedicated SCA chunk builder modules.

Handles: osv-scanner, pip-audit, npm-audit, composer-audit.
"""

import json
from datetime import UTC, datetime
from typing import Any

from core.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta


def _build_sca_chunks(
    builder: Any, result: ToolResult, profile: str
) -> list[tuple[str, dict[str, Any], str]]:
    """Build ChromaDB document chunks for any SCA tool result."""
    tool = result.tool_name
    parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
    vulnerabilities: list[dict[str, Any]] = parsed.get("vulnerabilities", [])

    timestamp = result.timestamp
    source_file = _first_output_file(result.output_files)
    ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    # Safe ID prefix: replace hyphens so doc IDs have consistent format
    tool_id = tool.replace("-", "_")

    chunks: list[tuple[str, dict[str, Any], str]] = []

    for vi, vuln in enumerate(vulnerabilities):
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

        fixed_str = fixed_version or "unknown"
        text = (
            f"[{tool}] [{severity.upper()}] vulnerability"
            f" in {pkg_name}@{pkg_version}\n"
            f"Vulnerability: {vuln_id}\n"
            f"Description: {summary}\n"
            f"Ecosystem: {ecosystem}\n"
            f"Fixed in: {fixed_str}\n"
            f"Source: {lockfile}"
        )

        meta: dict[str, Any] = {
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
            meta["description"] = summary
        if aliases:
            meta["aliases"] = ", ".join(aliases)
        if fixed_version:
            meta["fixed_version"] = fixed_version
        if introduced_version:
            meta["introduced_version"] = introduced_version
        if cvss_score is not None:
            meta["cvss_score"] = cvss_score
        if cvss_vector:
            meta["cvss_vector"] = cvss_vector
        if lockfile:
            meta["lockfile"] = lockfile
        if source_type:
            meta["source_type"] = source_type
        if details:
            meta["details"] = details
        if published:
            meta["published"] = published
        if modified:
            meta["modified"] = modified
        if references:
            meta["references"] = ", ".join(references)
        if cwe_ids:
            meta["cwe_ids"] = ", ".join(cwe_ids)
        meta.update(_shared_meta(builder, "dependency"))

        doc_id = f"{tool_id}_{profile}_vuln_{vi}_{ts_compact}"
        chunks.append((text, meta, doc_id))

    return chunks


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

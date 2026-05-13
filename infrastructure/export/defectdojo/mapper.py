"""Translate Tally Finding domain objects to DefectDojo Generic Findings
Import JSON format.

Pure function module with no I/O, network, or side effects.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.findings.entry import Finding

log = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, str] = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "informational": "Info",
}

_CONFIDENCE_MAP: dict[str, int] = {
    "confirmed": 100,
    "probable": 75,
    "potential": 50,
    "false_positive": 25,
}


def map_finding(finding: Finding) -> dict[str, Any]:
    """Map a single Finding to DefectDojo Generic Finding format."""
    base = _build_base(finding)

    tool = finding.tool or ""
    mapper = _TOOL_MAPPERS.get(tool)
    if mapper is not None:
        return mapper(finding, base)
    return base


def map_findings(findings: list[Finding]) -> list[dict[str, Any]]:
    """Map multiple findings, skipping any that fail to map."""
    results = []
    for finding in findings:
        try:
            results.append(map_finding(finding))
        except Exception as exc:
            log.warning(
                "Failed to map finding %d (tool=%s): %s",
                finding.id,
                finding.tool,
                exc,
            )
    return results


def _build_base(finding: Finding) -> dict[str, Any]:
    """Construct universal base dict for any finding."""
    base: dict[str, Any] = {}

    base["title"] = _synthesize_title(finding)
    base["severity"] = _SEVERITY_MAP.get(finding.severity or "", "Info")
    base["description"] = finding.description or base["title"]

    if finding.first_seen:
        base["date"] = finding.first_seen[:10]

    base["active"] = finding.status == "active" or finding.status is None
    base["verified"] = finding.confidence == "confirmed"
    base["false_p"] = finding.status == "false_positive"
    base["is_mitigated"] = finding.status == "fixed"
    base["static_finding"] = finding.domain == "code"
    base["dynamic_finding"] = finding.domain == "web"

    if finding.fingerprint:
        base["unique_id_from_tool"] = finding.fingerprint

    if finding.seen_count is not None:
        base["nb_occurences"] = finding.seen_count

    tags = _assemble_tags(finding)
    if tags:
        base["tags"] = tags

    if finding.meta.get("remediation"):
        base["mitigation"] = finding.meta["remediation"]

    cwe_int = _parse_cwe(finding.cwe)
    if cwe_int is not None:
        base["cwe"] = cwe_int

    if finding.vulnerability_id and finding.vulnerability_id.startswith("CVE-"):
        base["cve"] = finding.vulnerability_id

    if finding.vulnerability_id:
        base["vuln_id_from_tool"] = finding.vulnerability_id

    if finding.file:
        base["file_path"] = finding.file

    confidence_int = _map_confidence(finding.confidence)
    if confidence_int is not None:
        base["scanner_confidence"] = confidence_int

    return base


def _synthesize_title(finding: Finding) -> str:
    if finding.meta.get("title"):
        title = finding.meta["title"]
    else:
        rule = finding.rule_id or finding.meta.get("risk_type", "finding")
        location = finding.file or finding.url or "unknown"
        title = f"{finding.tool}: {rule} in {location}"

    return title[:255]


def _assemble_tags(finding: Finding) -> list[str]:
    tags = []

    if finding.finding_type:
        tags.extend(t for t in finding.finding_type if t is not None)

    if finding.domain:
        tags.append(f"domain:{finding.domain}")

    if finding.segment:
        tags.append(f"segment:{finding.segment}")

    if finding.tool:
        tags.append(f"tool:{finding.tool}")

    if finding.meta.get("tags"):
        meta_tags = finding.meta["tags"]
        if isinstance(meta_tags, list):
            tags.extend(t for t in meta_tags if t is not None)

    return [str(t) for t in tags if t]


def _parse_cwe(cwe_list: list[str]) -> int | None:
    """Extract first CWE number from list."""
    if not cwe_list:
        return None

    cwe_str = cwe_list[0]
    try:
        cwe_num = cwe_str.replace("CWE-", "").strip()
        return int(cwe_num)
    except (ValueError, AttributeError):
        return None


def _map_confidence(confidence: str | None) -> int | None:
    """Map confidence string to 0-100 int."""
    if confidence is None:
        return None
    return _CONFIDENCE_MAP.get(confidence)


def _map_semgrep(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add semgrep-specific fields."""
    if finding.meta.get("line_start") is not None:
        base["line"] = finding.meta["line_start"]

    if finding.file:
        base["sast_source_file_path"] = finding.file

    if finding.meta.get("references"):
        refs = finding.meta["references"]
        if isinstance(refs, list):
            base["references"] = "\n".join(str(r) for r in refs)

    return base


def _map_gitleaks(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add gitleaks-specific fields."""
    line = finding.meta.get("end_line") or finding.meta.get("line_number")
    if line is not None:
        base["line"] = line

    if finding.rule_id:
        base["vuln_id_from_tool"] = finding.rule_id

    return base


def _map_zap(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add ZAP-specific fields."""
    if finding.meta.get("param"):
        base["param"] = finding.meta["param"]

    if finding.url:
        base["endpoints"] = [finding.url]

    return base


def _map_xss_tool(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add XSS tool-specific fields (Dalfox, XSStrike)."""
    if finding.meta.get("param"):
        base["param"] = finding.meta["param"]

    if finding.meta.get("payload"):
        base["payload"] = finding.meta["payload"]

    if finding.url:
        base["endpoints"] = [finding.url]

    return base


def _map_garak(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add Garak-specific fields."""
    base["service"] = "llm"
    base["dynamic_finding"] = True

    description_parts = []

    if finding.meta.get("probe_description"):
        description_parts.append(finding.meta["probe_description"])

    if finding.meta.get("goal"):
        description_parts.append(f"Goal: {finding.meta['goal']}")

    if finding.description:
        description_parts.append(finding.description)

    if description_parts:
        base["description"] = "\n".join(description_parts)

    tags = base.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    if finding.meta.get("probe"):
        tags.append(f"probe:{finding.meta['probe']}")

    if finding.meta.get("detector"):
        tags.append(f"detector:{finding.meta['detector']}")

    if tags:
        base["tags"] = tags

    return base


def _map_sca(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Map SCA tools (OSV, npm-audit, pip-audit, composer-audit)."""
    if finding.package_name:
        base["component_name"] = finding.package_name

    if finding.package_version:
        base["component_version"] = finding.package_version

    if finding.meta.get("fixed_version"):
        base["fix_version"] = finding.meta["fixed_version"]

    if finding.meta.get("cvss_score") is not None:
        try:
            base["cvssv3_score"] = float(finding.meta["cvss_score"])
        except (ValueError, TypeError):
            pass

    if finding.meta.get("cvss_vector"):
        base["cvssv3"] = finding.meta["cvss_vector"]

    if finding.meta.get("references"):
        refs = finding.meta["references"]
        if isinstance(refs, list):
            base["references"] = "\n".join(str(r) for r in refs)

    if finding.meta.get("details"):
        base["impact"] = str(finding.meta["details"])[:500]

    return base


_TOOL_MAPPERS: dict[str, Callable[[Finding, dict[str, Any]], dict[str, Any]]] = {
    "semgrep": _map_semgrep,
    "gitleaks": _map_gitleaks,
    "zap": _map_zap,
    "dalfox": _map_xss_tool,
    "xsstrike": _map_xss_tool,
    "garak": _map_garak,
    "osv": _map_sca,
    "npm-audit": _map_sca,
    "pip-audit": _map_sca,
    "composer-audit": _map_sca,
}

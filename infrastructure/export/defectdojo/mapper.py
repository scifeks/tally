"""Translate Tally Finding domain objects to DefectDojo Generic Findings
Import JSON format.

Pure function module with no I/O, network, or side effects.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

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


_STATIC_ASSET_EXTENSIONS = frozenset(
    {
        ".js",
        ".css",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".map",
        ".webp",
        ".avif",
        ".bmp",
        ".cur",
        ".less",
        ".scss",
        ".sass",
        ".ts",
        ".mjs",
        ".cjs",
    }
)


def is_static_asset_path(path: str) -> bool:
    dot = path.rfind(".")
    if dot == -1:
        return False
    return path[dot:].lower() in _STATIC_ASSET_EXTENSIONS


def _clean_endpoint_url(raw_url: str) -> str:
    """Strip query params and fragments so DD gets a clean endpoint."""
    parsed = urlparse(raw_url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _map_semgrep(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add semgrep-specific fields."""
    if finding.meta.get("line_start") is not None:
        base["line"] = finding.meta["line_start"]

    if finding.meta.get("sast_source_file_path"):
        base["sast_source_file_path"] = finding.meta["sast_source_file_path"]
    elif finding.file:
        base["sast_source_file_path"] = finding.file

    if finding.meta.get("sast_source_line") is not None:
        base["sast_source_line"] = finding.meta["sast_source_line"]

    if finding.meta.get("sast_source_object"):
        base["sast_source_object"] = finding.meta["sast_source_object"]

    if finding.meta.get("sast_sink_object"):
        base["sast_sink_object"] = finding.meta["sast_sink_object"]

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

    if finding.url and not is_static_asset_path(urlparse(finding.url).path):
        base["endpoints"] = [_clean_endpoint_url(finding.url)]

    return base


def _map_xss_tool(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add XSS tool-specific fields (Dalfox, XSStrike)."""
    param = finding.meta.get("param", "")
    payload = finding.meta.get("payload", "")
    method = finding.meta.get("method", "")
    inject_type = finding.meta.get("inject_type", "")
    evidence = finding.meta.get("evidence", "")

    if param:
        base["param"] = param
    if payload:
        base["payload"] = payload

    if finding.url and not is_static_asset_path(urlparse(finding.url).path):
        base["endpoints"] = [_clean_endpoint_url(finding.url)]

    base["description"] = _build_xss_description(
        base.get("description", base.get("title", "")),
        param=param,
        payload=payload,
        method=method,
        inject_type=inject_type,
        evidence=evidence,
        poc_url=finding.url or "",
    )

    return base


def _build_xss_description(
    base_text: str,
    *,
    param: str,
    payload: str,
    method: str,
    inject_type: str,
    evidence: str,
    poc_url: str,
) -> str:
    parts = [base_text]
    if payload:
        parts.append(f"Payload: {payload}")
    if param:
        parts.append(f"Parameter: {param}")
    if method:
        parts.append(f"Method: {method}")
    if inject_type:
        parts.append(f"Inject type: {inject_type}")
    if evidence:
        parts.append(f"Evidence: {evidence}")
    if poc_url:
        parts.append(f"PoC URL: {poc_url}")
    return "\n".join(parts)


def _map_sqlmap(finding: Finding, base: dict[str, Any]) -> dict[str, Any]:
    """Add sqlmap-specific fields."""
    param = finding.meta.get("param", "")
    if param:
        base["param"] = param

    if finding.url and not is_static_asset_path(urlparse(finding.url).path):
        base["endpoints"] = [_clean_endpoint_url(finding.url)]

    dbms = finding.meta.get("dbms", "")
    technique_summary = finding.meta.get("technique_summary", "")
    payload = finding.meta.get("payload", "")

    desc_parts = [base.get("description", base.get("title", ""))]
    if dbms:
        desc_parts.append(f"DBMS: {dbms}")
    if technique_summary:
        desc_parts.append(f"Techniques: {technique_summary}")
    if payload:
        desc_parts.append(f"Payload: {payload}")

    base["description"] = "\n".join(desc_parts)

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
    "sqlmap": _map_sqlmap,
    "osv": _map_sca,
    "npm-audit": _map_sca,
    "pip-audit": _map_sca,
    "composer-audit": _map_sca,
}

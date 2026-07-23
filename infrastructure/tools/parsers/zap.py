"""Parser and handler for OWASP ZAP JSON/XML dynamic security scan output."""

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, cast

from domain.tools.base import ToolResult
from domain.tools.constants import CONFIDENCE_CONFIRMED
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)

# ZAP risk codes (riskcode field) and text names (riskdesc field) → severity label
_RISK_MAP: dict[str, str] = {
    "3": "high",
    "high": "high",
    "2": "medium",
    "medium": "medium",
    "1": "low",
    "low": "low",
    "0": "informational",
    "informational": "informational",
    "info": "informational",
}

# Alerts whose description starts with this prefix are ZAP self-diagnostics, not
# application findings. Suppress them before they enter the ingest pipeline.
_ZAP_VERSION_ALERT_PREFIX = (
    "The version of ZAP you are using to test your app is out of date"
)


def parse_zap_json(json_path: Path) -> dict[str, Any]:
    """Parse a ZAP JSON report file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_zap_data(data)


def parse_zap_json_string(json_string: str) -> dict[str, Any]:
    """Parse ZAP JSON from a raw string into structured data."""
    stripped = json_string.strip() if json_string else ""
    if not stripped:
        return _parse_zap_data({})
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string[:500]}
    return _parse_zap_data(data)


def parse_zap_xml(xml_path: Path) -> dict[str, Any]:
    """Parse a ZAP XML report file into structured data."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (OSError, ET.ParseError) as exc:
        return {"error": f"XML parse error: {exc}"}
    return _parse_zap_xml_root(root)


def _parse_zap_data(data: Any) -> dict[str, Any]:
    """Normalise the top-level ZAP JSON object into the canonical output dict."""
    if not isinstance(data, dict):
        return {"error": "Unexpected ZAP JSON format (expected object at root)"}

    alerts: list[dict[str, Any]] = []
    urls_scanned: set[str] = set()

    sites = data.get("site", [])
    if not isinstance(sites, list):
        sites = [sites] if sites else []

    for site in sites:
        if not isinstance(site, dict):
            continue
        for raw_alert in site.get("alerts", []):
            risk_raw = str(raw_alert.get("riskcode", raw_alert.get("riskdesc", "0")))
            if _normalize_risk(risk_raw) == "informational":
                continue
            expanded = _parse_alert(raw_alert)
            alerts.extend(expanded)
            for a in expanded:
                if a.get("url"):
                    urls_scanned.add(a["url"])

    by_risk: dict[str, int] = {}
    for alert in alerts:
        risk = alert.get("risk", "informational")
        by_risk[risk] = by_risk.get(risk, 0) + 1

    return {
        "alerts": alerts,
        "summary": {
            "total_alerts": len(alerts),
            "by_risk": by_risk,
            "urls_scanned": len(urls_scanned),
        },
    }


def _parse_alert(alert: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse one ZAP alert dict, expanding its ``instances`` into separate records."""
    alert_name = alert.get("name") or alert.get("alert", "")
    risk_raw = str(alert.get("riskcode", alert.get("riskdesc", "0")))
    risk = _normalize_risk(risk_raw)
    confidence = (
        alert.get("confidencedesc") or str(alert.get("confidence", "low"))
    ).lower()
    description = _strip_html(alert.get("desc", ""))
    solution = _extract_solution(alert)
    cwe_id = _to_int(alert.get("cweid"))
    if cwe_id is not None and cwe_id <= 0:
        cwe_id = None
    wasc_id = _to_int(alert.get("wascid"))

    instances: list[dict[str, Any]] = alert.get("instances", [])
    if not instances:
        return [
            _build_alert_record(
                alert_name,
                risk,
                confidence,
                description,
                solution,
                cwe_id,
                wasc_id,
                url="",
                method="",
                param=None,
                attack=None,
                evidence=None,
            )
        ]

    records = []
    for inst in instances:
        records.append(
            _build_alert_record(
                alert_name,
                risk,
                confidence,
                description,
                solution,
                cwe_id,
                wasc_id,
                url=inst.get("uri") or inst.get("url") or "",
                method=(inst.get("method") or "").upper(),
                param=inst.get("param") or None,
                attack=inst.get("attack") or None,
                evidence=inst.get("evidence") or None,
            )
        )
    return records


def _build_alert_record(
    alert_name: str,
    risk: str,
    confidence: str,
    description: str,
    solution: str,
    cwe_id: int | None,
    wasc_id: int | None,
    url: str,
    method: str,
    param: str | None,
    attack: str | None,
    evidence: str | None,
) -> dict[str, Any]:
    return {
        "alert_name": alert_name,
        "risk": risk,
        "confidence": confidence,
        "description": description,
        "url": url,
        "method": method,
        "param": param,
        "attack": attack,
        "evidence": evidence,
        "solution": solution,
        "cwe_id": cwe_id,
        "wasc_id": wasc_id,
    }


def _parse_zap_xml_root(root: ET.Element) -> dict[str, Any]:
    """Parse a ZAP XML report's root element into the canonical output dict."""
    alerts: list[dict[str, Any]] = []
    urls_scanned: set[str] = set()

    for alertitem in root.iter("alertitem"):
        risk_raw = (
            _xml_text(alertitem, "riskcode") or _xml_text(alertitem, "riskdesc") or "0"
        )
        risk = _normalize_risk(risk_raw)
        if risk == "informational":
            continue
        confidence = (_xml_text(alertitem, "confidencedesc") or "low").lower()
        alert_name = _xml_text(alertitem, "alert") or _xml_text(alertitem, "name")
        description = _strip_html(_xml_text(alertitem, "desc"))
        solution = (
            _strip_html(_xml_text(alertitem, "solution"))
            or "See OWASP ZAP documentation."
        )
        cwe_id = _to_int(_xml_text(alertitem, "cweid"))
        if cwe_id is not None and cwe_id <= 0:
            cwe_id = None
        wasc_id = _to_int(_xml_text(alertitem, "wascid"))

        instances_el = alertitem.find("instances")
        instances = instances_el.findall("instance") if instances_el is not None else []

        if not instances:
            alerts.append(
                _build_alert_record(
                    alert_name,
                    risk,
                    confidence,
                    description,
                    solution,
                    cwe_id,
                    wasc_id,
                    url="",
                    method="",
                    param=None,
                    attack=None,
                    evidence=None,
                )
            )
        else:
            for inst in instances:
                url = _xml_text(inst, "uri") or _xml_text(inst, "url") or ""
                alerts.append(
                    _build_alert_record(
                        alert_name,
                        risk,
                        confidence,
                        description,
                        solution,
                        cwe_id,
                        wasc_id,
                        url=url,
                        method=(_xml_text(inst, "method") or "").upper(),
                        param=_xml_text(inst, "param") or None,
                        attack=_xml_text(inst, "attack") or None,
                        evidence=_xml_text(inst, "evidence") or None,
                    )
                )
                if url:
                    urls_scanned.add(url)

    by_risk: dict[str, int] = {}
    for alert in alerts:
        r = alert.get("risk", "informational")
        by_risk[r] = by_risk.get(r, 0) + 1

    return {
        "alerts": alerts,
        "summary": {
            "total_alerts": len(alerts),
            "by_risk": by_risk,
            "urls_scanned": len(urls_scanned),
        },
    }


def _xml_text(element: ET.Element, tag: str) -> str:
    """Return text of a child element, or empty string."""
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else ""


# Shared parse helpers


def _normalize_risk(risk: str) -> str:
    """Map ZAP risk code or description to a lowercase severity label."""
    return _RISK_MAP.get(risk.lower(), _RISK_MAP.get(risk, "informational"))


def _extract_solution(alert: dict[str, Any]) -> str:
    raw = alert.get("solution", "")
    cleaned = _strip_html(raw) if raw else ""
    return cleaned or "See OWASP ZAP documentation."


def _strip_html(text: str) -> str:
    """Remove HTML tags from ZAP description/solution fields."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _to_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class ZapHandler:
    tool_name = "zap"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "remediation", "description"}
    )
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    # risk_type is already in metadata as alert_name so the metadata check filters
    # it out before any LLM call. Only owasp_name needs dedicated enrichment.
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("alert_name", "description", "cwe_id", "param", "evidence"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("alert_name", "url", "description", "param"),
            PromptStrategy.GENERIC,
        ),
    )
    normalized_fields: list[str] = [
        "confidence",
        "cwe",
        "finding_type",
        "method",
        "severity",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = cast(dict[str, Any], result.parsed_data or {})
        alerts: list[dict[str, Any]] = parsed.get("alerts", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for alert in alerts:
            description = alert.get("description", "")
            if description.startswith(_ZAP_VERSION_ALERT_PREFIX):
                logger.debug("Skipping ZAP self-diagnostic alert: %s", description[:80])
                continue

            alert_name = alert.get("alert_name", "")
            risk = alert.get("risk", "informational")
            raw_confidence = alert.get("confidence", "low")
            url = alert.get("url", "")
            method = alert.get("method", "")
            param = alert.get("param") or ""
            solution = alert.get("solution", "")
            cwe_id = alert.get("cwe_id")

            # Map ZAP confidence (text or integer string) to our constants
            _ZAP_CONFIDENCE: dict[str, str] = {
                "confirmed": CONFIDENCE_CONFIRMED,
                "4": CONFIDENCE_CONFIRMED,
                "high": "probable",
                "3": "probable",
                "medium": "probable",
                "2": "probable",
                "low": "potential",
                "1": "potential",
                "false positive": "potential",
                "0": "potential",
            }
            confidence = _ZAP_CONFIDENCE.get(str(raw_confidence).lower(), "potential")

            row: dict[str, Any] = {
                "tool": "zap",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": risk,
                "confidence": confidence,
                "risk_type": alert_name,
                "alert_name": alert_name,
                "url": url,
                "method": method.upper(),
                "description": description,
                "remediation": solution,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            evidence = alert.get("evidence") or ""
            if param:
                row["param"] = param
            if evidence:
                row["evidence"] = evidence
            if cwe_id is not None and cwe_id > 0:
                row["cwe_id"] = cwe_id
            if alert_name:
                row["title"] = alert_name
            row.update(_shared_meta(self, "vulnerability"))

            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Alert: {row.get('alert_name', '')}",
            f"URL: {row.get('url', '')}",
            f"Method: {row.get('method', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        if row.get("remediation"):
            parts.append(f"Remediation: {row['remediation']}")
        if row.get("cwe_id"):
            parts.append(f"CWE: {row['cwe_id']}")
        if row.get("param"):
            parts.append(f"Parameter: {row['param']}")
        if row.get("evidence"):
            parts.append(f"Evidence: {row['evidence']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")
        return "[zap] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "zap",
                str(finding.get("url", "")),
                str(finding.get("method", "")),
                str(finding.get("alert_name", "")),
            ]
        )

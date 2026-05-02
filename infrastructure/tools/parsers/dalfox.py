"""Parser and handler for DalFox XSS scan JSON output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)

# DalFox Type field values and their confidence mappings.
# V = verified (confirmed XSS), R = reflected, G = grep match.
_TYPE_CONFIDENCE: dict[str, str] = {
    "V": "confirmed",
    "R": "potential",
    "G": "potential",
}


# Parse functions


def parse_dalfox_json(json_path: Path) -> dict[str, Any]:
    """Parse a DalFox JSON output file into structured finding data."""
    try:
        text = json_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"JSON read error: {exc}", "findings": []}
    return parse_dalfox_json_string(text)


def parse_dalfox_json_string(json_string: str) -> dict[str, Any]:
    """Parse DalFox JSON output from a string into structured finding data."""
    if not json_string or not json_string.strip():
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        logger.warning("DalFox: JSON decode error: %s", exc)
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    if not isinstance(data, list):
        logger.warning("DalFox: expected JSON array, got %s", type(data).__name__)
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    return _parse_dalfox_data(data)


# Internal helpers


def _parse_dalfox_data(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalise a list of DalFox PoC objects into the standard finding shape."""
    findings: list[dict[str, Any]] = []

    for item in data:
        if not isinstance(item, dict):
            continue
        # Skip empty placeholder objects (e.g. [{}] when no findings).
        if not item:
            continue

        poc = item.get("PoC", "")
        param = item.get("Param", "")
        payload = item.get("Payload", "")
        cwe = item.get("CWE", "")
        severity = (item.get("Severity") or "medium").lower()
        inject_type = item.get("InjectType", "")
        method = item.get("Method", "GET")
        evidence = item.get("Evidence", "")
        message = item.get("MessageStr", "")
        raw_type = item.get("Type", "R")
        confidence = _TYPE_CONFIDENCE.get(raw_type, "potential")

        findings.append(
            {
                "url": poc,
                "param": param,
                "payload": payload,
                "cwe": cwe,
                "severity": severity,
                "inject_type": inject_type,
                "method": method,
                "evidence": evidence,
                "message": message,
                "confidence": confidence,
            }
        )

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


# Handler


class DalFoxHandler:
    tool_name = "dalfox"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity", "confidence"})
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("risk_type", "param", "payload", "url"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("risk_type", "url", "param"),
            PromptStrategy.GENERIC,
        ),
    )
    normalized_fields: list[str] = [
        "confidence",
        "cwe",
        "finding_type",
        "method",
        "param",
        "payload",
        "poc",
        "severity",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            url = finding.get("url", "")
            param = finding.get("param", "")
            payload = finding.get("payload", "")
            cwe_raw = finding.get("cwe", "")
            # Normalise "CWE-79" → 79 (integer), or fall back to 79.
            cwe_id: int = 79
            if cwe_raw:
                try:
                    cwe_id = int(str(cwe_raw).replace("CWE-", "").strip())
                except ValueError:
                    cwe_id = 79

            row: dict[str, Any] = {
                "tool": "dalfox",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": finding.get("severity", "medium"),
                "confidence": finding.get("confidence", "potential"),
                "risk_type": "Cross-Site Scripting (XSS)",
                "cwe_id": cwe_id,
                "url": url,
                "poc": url,
                "param": param,
                "payload": payload,
                "method": finding.get("method", "GET"),
                "timestamp": timestamp,
                "source_file": source_file,
            }
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            "Tool: dalfox",
            f"URL: {row.get('url', '')}",
            f"Parameter: {row.get('param', '')}",
            f"Payload: {row.get('payload', '')}",
            f"Method: {row.get('method', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
            f"CWE: {row.get('cwe_id', 79)}",
        ]
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        return "[dalfox] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "dalfox",
                str(finding.get("url", "")),
                str(finding.get("param", "")),
                str(finding.get("payload", "")),
            ]
        )

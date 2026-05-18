"""Parser and handler for Nuclei vulnerability scanner JSON output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)


def parse_nuclei_json(json_path: Path) -> dict[str, Any]:
    """Parse a Nuclei JSON output file into structured finding data."""
    try:
        text = json_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"JSON read error: {exc}", "findings": []}
    return parse_nuclei_json_string(text)


def parse_nuclei_json_string(json_string: str) -> dict[str, Any]:
    """Parse Nuclei JSON output from a string into structured finding data."""
    if not json_string or not json_string.strip():
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    try:
        entries = json.loads(json_string)
    except json.JSONDecodeError as exc:
        logger.warning("Nuclei: JSON decode error: %s", exc)
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    if not isinstance(entries, list):
        logger.warning("Nuclei: expected JSON array, got %s", type(entries).__name__)
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    return _parse_nuclei_data(entries)


def _parse_nuclei_data(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize a list of Nuclei result objects into the standard finding shape."""
    findings: list[dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not entry:
            continue

        finding = _parse_finding(entry)
        findings.append(finding)

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


def _parse_finding(raw_finding: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized fields from a single Nuclei result."""
    template_info = raw_finding.get("info", {})
    if not isinstance(template_info, dict):
        template_info = {}

    classification = template_info.get("classification", {})
    if not isinstance(classification, dict):
        classification = {}

    template_id = raw_finding.get("template-id", "")
    matched_at = raw_finding.get("matched-at", "")
    url = matched_at or raw_finding.get("host", "")
    vulnerability_id = classification.get("cve-id") or None
    tags = template_info.get("tags", [])
    if isinstance(tags, list):
        tags_str = ",".join(tags)
    else:
        tags_str = str(tags)

    return {
        "template_id": template_id,
        "severity": (template_info.get("severity", "medium") or "medium").lower(),
        "description": template_info.get("description", ""),
        "url": url,
        "matched_at": matched_at,
        "vulnerability_id": vulnerability_id,
        "name": template_info.get("name", ""),
        "tags": tags_str,
        "host": raw_finding.get("host", ""),
        "type": raw_finding.get("type", ""),
        "matcher_name": raw_finding.get("matcher-name", ""),
        "timestamp": raw_finding.get("timestamp", ""),
    }


class NucleiHandler:
    tool_name = "nuclei"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "description", "vulnerability_id"}
    )
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability"},
        "misconfiguration": {"type_misconfiguration"},
        "exposure": {"type_exposure"},
    }
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("vulnerability_id", "description", "rule_id"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "risk_type",
            ("description", "rule_id", "url"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "remediation",
            ("vulnerability_id", "description", "rule_id"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "title",
            ("rule_id", "url", "description"),
            PromptStrategy.GENERIC,
        ),
    )
    normalized_fields: list[str] = [
        "confidence",
        "finding_type",
        "host",
        "matched_at",
        "matcher_name",
        "severity",
        "tags",
        "template_id",
        "type",
        "url",
        "vulnerability_id",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            tags_str = finding.get("tags", "")
            vulnerability_id = finding.get("vulnerability_id")

            if tags_str:
                tags_lower = tags_str.lower()
            else:
                tags_lower = ""

            if "cve" in tags_lower or vulnerability_id:
                finding_type_key = "vulnerability"
            elif "misconfig" in tags_lower:
                finding_type_key = "misconfiguration"
            elif "exposure" in tags_lower:
                finding_type_key = "exposure"
            else:
                finding_type_key = "vulnerability"

            row: dict[str, Any] = {
                "tool": "nuclei",
                "profile": profile,
                "finding_type": json.dumps([finding_type_key]),
                "severity": finding.get("severity", "medium"),
                "confidence": "confirmed",
                "rule_id": finding.get("template_id", ""),
                "url": finding.get("url", ""),
                "vulnerability_id": vulnerability_id,
                "description": finding.get("description", ""),
                "host": finding.get("host", ""),
                "matched_at": finding.get("matched_at", ""),
                "template_id": finding.get("template_id", ""),
                "matcher_name": finding.get("matcher_name", ""),
                "tags": tags_str,
                "type": finding.get("type", ""),
                "timestamp": timestamp,
                "source_file": source_file,
            }
            row.update(_shared_meta(self, finding_type_key))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Template: {row.get('template_id', '')}",
            f"URL: {row.get('url', '')}",
            f"Severity: {row.get('severity', '')}",
        ]
        if row.get("vulnerability_id"):
            parts.append(f"CVE: {row['vulnerability_id']}")
        return "[nuclei] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "nuclei",
                str(finding.get("template_id", finding.get("rule_id", ""))),
                str(finding.get("matched_at", finding.get("url", ""))),
            ]
        )

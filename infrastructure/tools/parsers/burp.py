"""Parser for Burp Suite REST API issue events."""

from __future__ import annotations

import json as _json
import logging
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.burp.confidence import (
    determine_finding_status,
    map_burp_confidence,
    parse_fingerprint,
)
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy
from infrastructure.tools.burp.evidence import decode_evidence
from infrastructure.tools.parsers._shared import _first_output_file, _shared_meta

_log = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, str] = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "informational",
    "information": "informational",
    "informational": "informational",
    "false_positive": "informational",
}


def parse_burp_issue_events(
    issue_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Parse Burp REST API issue events into Tally findings.

    Only processes events with type "issue_found". Other event types
    (issue_updated, etc.) are silently skipped.
    """
    findings: list[dict[str, Any]] = []
    for event in issue_events:
        if event.get("type") != "issue_found":
            continue
        issue = event.get("issue")
        if not issue:
            continue
        parsed = _parse_issue(issue)
        if parsed is not None:
            findings.append(parsed)

    by_severity: dict[str, int] = {}
    for f in findings:
        sev = f["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_severity": by_severity,
        },
    }


def _parse_issue(issue: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single Burp issue dict into a Tally finding."""
    name = issue.get("name", "")
    if not name:
        return None

    origin = issue.get("origin", "")
    path = issue.get("path", "")
    url = f"{origin}{path}" if origin else path

    raw_severity = issue.get("severity", "info")
    severity = _SEVERITY_MAP.get(raw_severity.lower(), "informational")

    raw_confidence = issue.get("confidence", "tentative")
    confidence = map_burp_confidence(raw_confidence)

    evidence_list = issue.get("evidence", [])
    evidence_text = decode_evidence(evidence_list)

    fingerprint_raw = issue.get("fingerprint", "")
    fp_fields = parse_fingerprint(fingerprint_raw)

    return {
        "name": name,
        "origin": origin,
        "path": path,
        "url": url,
        "severity": severity,
        "confidence": confidence,
        "status": determine_finding_status(),
        "description": issue.get("description", ""),
        "remediation": issue.get("remediation", ""),
        "type_index": issue.get("type_index"),
        "serial_number": issue.get("serial_number", ""),
        "evidence": evidence_text,
        "fingerprint_raw": fingerprint_raw,
        "fingerprint_type": fp_fields.get("type", ""),
        "fingerprint_origin": fp_fields.get("origin", ""),
        "fingerprint_path": fp_fields.get("path", ""),
    }


class BurpHandler:
    """Handler that normalizes parsed Burp findings into DB rows."""

    tool_name = "burp"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "remediation", "description"}
    )
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("alert_name", "description", "fingerprint_type"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("alert_name", "url", "description"),
            PromptStrategy.GENERIC,
        ),
    )
    normalized_fields: list[str] = [
        "confidence",
        "finding_type",
        "method",
        "severity",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed = result.parsed_data or {}
        findings: list[dict] = parsed.get("findings", [])
        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []
        for finding in findings:
            alert_name = finding.get("name", "")
            row: dict = {
                "tool": "burp",
                "profile": profile,
                "finding_type": _json.dumps(["vulnerability"]),
                "severity": finding.get("severity", "informational"),
                "confidence": finding.get("confidence", "potential"),
                "risk_type": alert_name,
                "alert_name": alert_name,
                "url": finding.get("url", ""),
                "method": "",
                "description": finding.get("description", ""),
                "remediation": finding.get("remediation", ""),
                "timestamp": timestamp,
                "source_file": source_file,
                "fingerprint_type": finding.get("fingerprint_type", ""),
            }
            evidence = finding.get("evidence", "")
            if evidence:
                row["evidence"] = evidence
            if alert_name:
                row["title"] = alert_name
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Alert: {row.get('alert_name', '')}",
            f"URL: {row.get('url', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        if row.get("remediation"):
            parts.append(f"Remediation: {row['remediation']}")
        if row.get("evidence"):
            parts.append(f"Evidence: {row['evidence'][:200]}")
        return "[burp] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict) -> str:
        return "|".join(
            [
                "burp",
                str(finding.get("url", "")),
                str(finding.get("alert_name", "")),
                str(finding.get("fingerprint_type", "")),
            ]
        )

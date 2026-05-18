"""Parser and handler for sqlmap SQL injection scan output."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import (
    FieldEnrichmentSpec,
    PromptStrategy,
)

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)

_PARAM_HEADER_RE = re.compile(r"Parameter:\s+(\S+)\s+\((\w+)\)")
_TECHNIQUE_RE = re.compile(
    r"^\s+Type:\s+(.+?)\s*$\n"
    r"^\s+Title:\s+(.+?)\s*$\n"
    r"^\s+Payload:\s+(.+?)\s*$",
    re.MULTILINE,
)
_DBMS_RE = re.compile(r"back-end DBMS:\s+(.+)", re.IGNORECASE)
_WEBAPP_TECH_RE = re.compile(r"web application technology:\s+(.+)", re.IGNORECASE)
_TARGET_URL_RE = re.compile(
    r"^(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)"
    r"\s+(https?://\S+)",
    re.MULTILINE | re.IGNORECASE,
)
_QUOTED_URL_RE = re.compile(
    r"(?:testing URL|flushing session file for"
    r"|resuming .+ for)\s+'(https?://[^']+)'",
    re.IGNORECASE,
)
_BARE_URL_RE = re.compile(r"(https?://\S+)")
_BLOCK_DELIM_RE = re.compile(r"^---\s*$", re.MULTILINE)


def parse_sqlmap_output(path: Path) -> dict[str, Any]:
    """Parse a sqlmap output file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"Read error: {exc}", "findings": []}
    return parse_sqlmap_output_string(text)


def parse_sqlmap_output_string(text: str) -> dict[str, Any]:
    """Parse sqlmap stdout into structured finding data."""
    if not text or not text.strip():
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }

    dbms = ""
    webapp_tech = ""
    for m in _DBMS_RE.finditer(text):
        dbms = m.group(1).strip()
    for m in _WEBAPP_TECH_RE.finditer(text):
        webapp_tech = m.group(1).strip()

    delimiters = [m.start() for m in _BLOCK_DELIM_RE.finditer(text)]

    findings: list[dict[str, Any]] = []

    i = 0
    while i < len(delimiters) - 1:
        block_start = delimiters[i]
        block_end = delimiters[i + 1]
        block = text[block_start:block_end]

        if not _PARAM_HEADER_RE.search(block):
            i += 1
            continue

        preceding = text[:block_start]
        url = _extract_url(preceding)

        after = text[block_end : block_end + 500]
        local_dbms = _DBMS_RE.search(after)
        block_dbms = local_dbms.group(1).strip() if local_dbms else dbms
        local_tech = _WEBAPP_TECH_RE.search(after)
        block_tech = local_tech.group(1).strip() if local_tech else webapp_tech

        for section in re.split(r"(?=Parameter:\s+)", block):
            param_match = _PARAM_HEADER_RE.search(section)
            if not param_match:
                continue

            param_name = param_match.group(1)
            param_method = param_match.group(2).upper()

            techniques = []
            for tm in _TECHNIQUE_RE.finditer(section):
                techniques.append(
                    {
                        "type": tm.group(1).strip(),
                        "title": tm.group(2).strip(),
                        "payload": tm.group(3).strip(),
                    }
                )

            if techniques:
                findings.append(
                    {
                        "url": url,
                        "param": param_name,
                        "method": param_method,
                        "dbms": block_dbms,
                        "webapp_technology": block_tech,
                        "techniques": techniques,
                    }
                )

        i += 2

    return {
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "dbms": dbms,
        },
    }


def _extract_url(text: str) -> str:
    """Extract the most recent target URL from preceding text."""
    matches = list(_TARGET_URL_RE.finditer(text))
    if matches:
        return matches[-1].group(1).strip()

    matches = list(_QUOTED_URL_RE.finditer(text))
    if matches:
        return matches[-1].group(1).strip()

    matches = list(_BARE_URL_RE.finditer(text))
    if matches:
        return matches[-1].group(0).strip()

    return ""


class SqlmapHandler:
    tool_name = "sqlmap"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "description"}
    )
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("risk_type", "param", "url"),
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
        "cwe_id",
        "dbms",
        "finding_type",
        "method",
        "param",
        "payload",
        "severity",
        "technique_summary",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            url = finding.get("url", "")
            param = finding.get("param", "")
            method = finding.get("method", "GET")
            found_dbms = finding.get("dbms", "")
            techniques = finding.get("techniques", [])
            tech_val = finding.get("webapp_technology", "")

            technique_names = [t["type"] for t in techniques]
            has_stacked = any("stacked" in t.lower() for t in technique_names)
            severity = "critical" if has_stacked else "high"

            technique_summary = ", ".join(technique_names)
            payloads = [t.get("payload", "") for t in techniques if t.get("payload")]

            desc_parts = [
                f"SQL injection in '{param}' parameter ({method})",
            ]
            if found_dbms:
                desc_parts.append(f"DBMS: {found_dbms}")
            if technique_summary:
                desc_parts.append(f"Techniques: {technique_summary}")

            row: dict[str, Any] = {
                "tool": "sqlmap",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": severity,
                "confidence": "confirmed",
                "risk_type": "SQL Injection",
                "cwe_id": 89,
                "url": url,
                "param": param,
                "method": method,
                "dbms": found_dbms,
                "webapp_technology": tech_val,
                "techniques": json.dumps(techniques),
                "technique_summary": technique_summary,
                "payload": payloads[0] if payloads else "",
                "description": ". ".join(desc_parts),
                "timestamp": timestamp,
                "source_file": source_file,
                "title": (
                    f"SQL Injection in '{param}' ({method})"
                    if param
                    else "SQL Injection"
                ),
            }
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            "Tool: sqlmap",
            f"URL: {row.get('url', '')}",
            f"Parameter: {row.get('param', '')}",
            f"Method: {row.get('method', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
            f"CWE: {row.get('cwe_id', 89)}",
        ]
        if row.get("dbms"):
            parts.append(f"DBMS: {row['dbms']}")
        if row.get("technique_summary"):
            parts.append(f"Techniques: {row['technique_summary']}")
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        return "[sqlmap] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "sqlmap",
                str(finding.get("url", "")),
                str(finding.get("param", "")),
                str(finding.get("method", "")),
            ]
        )

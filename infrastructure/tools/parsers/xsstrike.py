"""Parser and handler for XSStrike XSS scan log output."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)

# Strip ANSI escape sequences produced by XSStrike's coloured console output.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Match the "Vulnerable webpage" VULN line (file log or console log format).
# File format:  "2024-01-01 12:00:00,000 xsstrike - VULN - Vulnerable webpage: <url>"
# Console fmt:  "[++] Vulnerable webpage: <url>"
_VULN_URL_RE = re.compile(r"Vulnerable webpage:\s*(.+)")

# Match the "Vector for" VULN line in both formats.
# File format:  "... xsstrike - VULN - Vector for <param>: <payload>"
# Console fmt:  "[++] Vector for <param>: <payload>"
_VULN_VEC_RE = re.compile(r"Vector for\s+(.+?):\s*(.+)")


# ---------------------------------------------------------------------------
# Parse functions
# ---------------------------------------------------------------------------


def parse_xsstrike_log(log_path: Path) -> dict[str, Any]:
    """Parse an XSStrike log file into structured finding data."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"Log read error: {exc}", "findings": []}
    return parse_xsstrike_log_string(text)


def parse_xsstrike_log_string(text: str) -> dict[str, Any]:
    """Parse XSStrike log content from a string into structured finding data."""
    if not text or not text.strip():
        return {"findings": [], "summary": {"total_findings": 0}}
    lines = text.splitlines()
    return _parse_xsstrike_lines(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_ansi(line: str) -> str:
    return _ANSI_RE.sub("", line).strip()


def _parse_xsstrike_lines(lines: list[str]) -> dict[str, Any]:
    """Correlate consecutive VULN URL + vector line pairs into findings."""
    findings: list[dict[str, Any]] = []
    pending_url: str | None = None

    for raw_line in lines:
        line = _strip_ansi(raw_line)
        if not line:
            continue

        url_match = _VULN_URL_RE.search(line)
        if url_match:
            if pending_url is not None:
                # Unpaired URL — previous URL had no matching vector line.
                logger.warning(
                    "XSStrike: unpaired 'Vulnerable webpage' line (no vector "
                    "followed): %s",
                    pending_url,
                )
            pending_url = url_match.group(1).strip()
            continue

        vec_match = _VULN_VEC_RE.search(line)
        if vec_match:
            if pending_url is None:
                # Vector line with no preceding URL line — skip.
                logger.warning(
                    "XSStrike: 'Vector for' line with no preceding URL: %s",
                    line[:120],
                )
                continue
            param = vec_match.group(1).strip()
            payload = vec_match.group(2).strip()
            findings.append(
                {
                    "url": pending_url,
                    "param": param,
                    "payload": payload,
                }
            )
            pending_url = None

    if pending_url is not None:
        logger.warning(
            "XSStrike: trailing unpaired 'Vulnerable webpage' line: %s",
            pending_url,
        )

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class XSSTrikeHandler:
    tool_name = "xsstrike"
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
        "param",
        "payload",
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

            row: dict[str, Any] = {
                "tool": "xsstrike",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": "high",
                "confidence": "potential",
                "risk_type": "Cross-Site Scripting (XSS)",
                "cwe_id": 79,
                "url": url,
                "param": param,
                "payload": payload,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            "Tool: xsstrike",
            f"URL: {row.get('url', '')}",
            f"Parameter: {row.get('param', '')}",
            f"Payload: {row.get('payload', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
            f"CWE: {row.get('cwe_id', 79)}",
        ]
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        return "[xsstrike] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "xsstrike",
                str(finding.get("url", "")),
                str(finding.get("param", "")),
                str(finding.get("payload", "")),
            ]
        )

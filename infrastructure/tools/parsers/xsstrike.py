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

# retireJs plugin line patterns.
# "plugins.retireJs - GOOD - Vulnerable component: jquery v3.2.1"
_RETIREJS_COMPONENT_RE = re.compile(
    r"plugins\.retireJs\s+-\s+GOOD\s+-\s+Vulnerable component:\s*(.+)"
)
# "plugins.retireJs - INFO - Component location: <url>"
_RETIREJS_LOCATION_RE = re.compile(
    r"plugins\.retireJs\s+-\s+INFO\s+-\s+Component location:\s*(.+)"
)
# "plugins.retireJs - INFO - Summary: <text>"
_RETIREJS_SUMMARY_RE = re.compile(
    r"plugins\.retireJs\s+-\s+INFO\s+-\s+(?:\[92m)?Summary:(?:\[0m)?\s*(.+)"
)
# "plugins.retireJs - INFO - Severity: <level>"
_RETIREJS_SEVERITY_RE = re.compile(
    r"plugins\.retireJs\s+-\s+INFO\s+-\s+Severity:\s*(.+)"
)
# "plugins.retireJs - INFO - CVE: <cve-id>"
_RETIREJS_CVE_RE = re.compile(r"plugins\.retireJs\s+-\s+INFO\s+-\s+CVE:\s*(.+)")
# Any retireJs INFO/GOOD line (used to detect we're still inside a block).
_RETIREJS_ANY_RE = re.compile(r"plugins\.retireJs\s+-\s+")


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
        return {
            "findings": [],
            "component_findings": [],
            "summary": {"total_findings": 0},
        }
    lines = text.splitlines()
    return _parse_xsstrike_lines(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_ansi(line: str) -> str:
    return _ANSI_RE.sub("", line).strip()


def _flush_retirejs(
    pending: dict[str, Any],
    component_findings: list[dict[str, Any]],
) -> None:
    """Flush a pending retireJs block into component_findings if it has a name."""
    if pending.get("component_name"):
        component_findings.append(dict(pending))
    pending.clear()


def _parse_xsstrike_lines(lines: list[str]) -> dict[str, Any]:
    """Correlate VULN line pairs and retireJs blocks into findings."""
    findings: list[dict[str, Any]] = []
    component_findings: list[dict[str, Any]] = []
    pending_url: str | None = None
    pending_retirejs: dict[str, Any] = {}

    for raw_line in lines:
        line = _strip_ansi(raw_line)
        if not line:
            continue

        # --- retireJs block parsing ---
        component_match = _RETIREJS_COMPONENT_RE.search(line)
        if component_match:
            # New component block — flush any previous pending block first.
            _flush_retirejs(pending_retirejs, component_findings)
            raw_component = component_match.group(1).strip()
            # Split "jquery v3.2.1" → name="jquery", version="3.2.1"
            parts = raw_component.rsplit(" ", 1)
            name = parts[0].strip()
            version = parts[1].strip().lstrip("v") if len(parts) == 2 else ""
            pending_retirejs = {
                "component_name": name,
                "component_version": version,
            }
            continue

        if _RETIREJS_ANY_RE.search(line):
            # We're inside a retireJs block — accumulate fields.
            loc_match = _RETIREJS_LOCATION_RE.search(line)
            if loc_match:
                pending_retirejs["component_location"] = loc_match.group(1).strip()
                continue

            summary_match = _RETIREJS_SUMMARY_RE.search(line)
            if summary_match:
                pending_retirejs["summary"] = summary_match.group(1).strip()
                continue

            severity_match = _RETIREJS_SEVERITY_RE.search(line)
            if severity_match:
                pending_retirejs["severity"] = severity_match.group(1).strip().lower()
                continue

            cve_match = _RETIREJS_CVE_RE.search(line)
            if cve_match:
                pending_retirejs["cve"] = cve_match.group(1).strip()
                continue

            # Other retireJs INFO lines (e.g. "Total vulnerabilities:") —
            # ignore but stay in block.
            continue

        # Non-retireJs line — flush any open retireJs block.
        if pending_retirejs:
            _flush_retirejs(pending_retirejs, component_findings)
            pending_retirejs = {}

        # --- VULN pair parsing ---
        url_match = _VULN_URL_RE.search(line)
        if url_match:
            if pending_url is not None:
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

    # Flush any trailing retireJs block.
    if pending_retirejs:
        _flush_retirejs(pending_retirejs, component_findings)

    if pending_url is not None:
        logger.warning(
            "XSStrike: trailing unpaired 'Vulnerable webpage' line: %s",
            pending_url,
        )

    total = len(findings) + len(component_findings)
    return {
        "findings": findings,
        "component_findings": component_findings,
        "summary": {"total_findings": total},
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
        "description",
        "finding_type",
        "package_name",
        "package_version",
        "param",
        "payload",
        "severity",
        "url",
        "vulnerability_id",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])
        component_findings: list[dict[str, Any]] = parsed.get("component_findings", [])

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

        for cf in component_findings:
            row = {
                "tool": "xsstrike",
                "profile": profile,
                "finding_type": json.dumps(["dependency"]),
                "severity": cf.get("severity", "low"),
                "confidence": "confirmed",
                "risk_type": "Vulnerable Component",
                "package_name": cf.get("component_name", ""),
                "package_version": cf.get("component_version", ""),
                "vulnerability_id": cf.get("cve", ""),
                "url": cf.get("component_location", ""),
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if cf.get("summary"):
                row["description"] = cf["summary"]
            row.update(_shared_meta(self, "dependency"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        if row.get("package_name"):
            parts = [
                "Tool: xsstrike",
                f"Component: {row.get('package_name', '')}@"
                f"{row.get('package_version', '')}",
                f"CVE: {row.get('vulnerability_id', '')}",
                f"Severity: {row.get('severity', '')}",
                f"URL: {row.get('url', '')}",
            ]
            if row.get("description"):
                parts.append(f"Description: {row['description']}")
            if row.get("risk_type"):
                parts.append(f"Risk type: {row['risk_type']}")
        else:
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
        if finding.get("package_name"):
            return "|".join(
                [
                    "xsstrike",
                    str(finding.get("package_name", "")),
                    str(finding.get("vulnerability_id", "")),
                    str(finding.get("url", "")),
                ]
            )
        return "|".join(
            [
                "xsstrike",
                str(finding.get("url", "")),
                str(finding.get("param", "")),
                str(finding.get("payload", "")),
            ]
        )

"""Parser and handler for ffuf web fuzzer JSON output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)


def parse_ffuf_json(json_path: Path) -> dict[str, Any]:
    """Parse a ffuf JSON output file into structured finding data."""
    try:
        text = json_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"JSON read error: {exc}", "findings": []}
    return parse_ffuf_json_string(text)


def parse_ffuf_json_string(json_string: str) -> dict[str, Any]:
    """Parse ffuf JSON output from a string into structured finding data."""
    if not json_string or not json_string.strip():
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        logger.warning("ffuf: JSON decode error: %s", exc)
        return {"error": f"JSON decode error: {exc}", "findings": []}
    if not isinstance(data, dict):
        logger.warning("ffuf: expected JSON object, got %s", type(data).__name__)
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }
    return _parse_ffuf_data(data)


def _parse_ffuf_data(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a ffuf results object into the standard finding shape."""
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []

    findings: list[dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue
        if not item:
            continue

        finding = _parse_finding(item)
        findings.append(finding)

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


def _severity_from_status(status: int) -> str:
    """Map HTTP status code to severity level."""
    if status == 403:
        return "low"
    return "informational"


def _parse_finding(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized fields from a single ffuf result."""
    url = raw.get("url", "")
    status = raw.get("status", 0)
    content_type = raw.get("content-type", "")
    host = raw.get("host", "")
    redirect_location = raw.get("redirectlocation", "")
    length = raw.get("length", 0)
    words = raw.get("words", 0)
    lines = raw.get("lines", 0)
    fuzz_input = raw.get("input", {})
    if not isinstance(fuzz_input, dict):
        fuzz_input = {}

    severity = _severity_from_status(status)

    return {
        "url": url,
        "status": status,
        "length": length,
        "words": words,
        "lines": lines,
        "content_type": content_type,
        "host": host,
        "redirect_location": redirect_location,
        "severity": severity,
        "input": fuzz_input,
    }


class FfufHandler:
    tool_name = "ffuf"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {"exposure": {"type_exposure"}}
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "risk_type",
            ("url", "status", "content_type"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "title",
            ("url", "status", "content_type"),
            PromptStrategy.GENERIC,
        ),
    )
    normalized_fields: list[str] = [
        "content_type",
        "finding_type",
        "host",
        "length",
        "redirect_location",
        "severity",
        "status",
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
            status = finding.get("status", 0)
            content_type = finding.get("content_type", "")

            row: dict[str, Any] = {
                "tool": "ffuf",
                "profile": profile,
                "finding_type": json.dumps(["exposure"]),
                "severity": finding.get("severity", "informational"),
                "confidence": "confirmed",
                "url": url,
                "status": status,
                "length": finding.get("length", 0),
                "words": finding.get("words", 0),
                "lines": finding.get("lines", 0),
                "content_type": content_type,
                "host": finding.get("host", ""),
                "redirect_location": finding.get("redirect_location", ""),
                "timestamp": timestamp,
                "source_file": source_file,
            }
            row.update(_shared_meta(self, "exposure"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"URL: {row.get('url', '')}",
            f"Status: {row.get('status', '')}",
            f"Severity: {row.get('severity', '')}",
        ]
        content_type = row.get("content_type", "")
        if content_type:
            parts.append(f"Content-Type: {content_type}")
        redirect = row.get("redirect_location", "")
        if redirect:
            parts.append(f"Redirect: {redirect}")
        return "[ffuf] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "ffuf",
                str(finding.get("url", "")),
                str(finding.get("status", "")),
            ]
        )

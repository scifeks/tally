"""Parser and handler for graphql-cop JSON output."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, str] = {
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFO": "informational",
}


def _empty() -> dict[str, Any]:
    return {"findings": [], "summary": {"total_findings": 0}}


def parse_graphql_cop_json(json_path: Path) -> dict[str, Any]:
    """Parse a graphql-cop JSON output file."""
    try:
        text = json_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"JSON read error: {exc}", "findings": []}
    return parse_graphql_cop_json_string(text)


def parse_graphql_cop_json_string(json_string: str) -> dict[str, Any]:
    """Parse graphql-cop JSON from a raw string."""
    if not json_string or not json_string.strip():
        return _empty()
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        logger.warning("graphql-cop: JSON decode error: %s", exc)
        return _empty()
    if not isinstance(data, list):
        logger.warning(
            "graphql-cop: expected JSON array, got %s",
            type(data).__name__,
        )
        return _empty()
    return _parse_data(data)


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _parse_data(checks: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    for check in checks:
        if not isinstance(check, dict):
            continue
        if not check.get("result"):
            continue

        raw_severity = check.get("severity", "LOW")
        severity = _SEVERITY_MAP.get(str(raw_severity).upper(), "low")

        findings.append(
            {
                "title": check.get("title", ""),
                "severity": severity,
                "description": check.get("description", ""),
                "impact": check.get("impact", ""),
                "curl_verify": check.get("curl_verify", ""),
            }
        )

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


class GraphqlCopHandler:
    tool_name = "graphql-cop"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity", "description"})
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability"},
    }
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "risk_type",
            ("rule_id", "description", "severity"),
        ),
        FieldEnrichmentSpec("remediation", ("rule_id", "description")),
        FieldEnrichmentSpec("confidence", ("rule_id", "severity")),
        FieldEnrichmentSpec("title", ("rule_id", "description", "url")),
    )
    normalized_fields: list[str] = [
        "description",
        "finding_type",
        "rule_id",
        "severity",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])
        target_url: str = parsed.get("target_url", "")
        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []
        for finding in findings:
            title = finding.get("title", "")
            slug = _slugify(title)

            row: dict[str, Any] = {
                "tool": "graphql-cop",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": finding.get("severity", "low"),
                "description": finding.get("description", ""),
                "rule_id": slug,
                "url": target_url,
                "title": title,
                "timestamp": timestamp,
                "source_file": source_file,
                "meta": {
                    "impact": finding.get("impact", ""),
                    "curl_verify": finding.get("curl_verify", ""),
                    "title_raw": title,
                },
            }
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        severity = row.get("severity", "")
        title = row.get("title", "")
        url = row.get("url", "")
        return f"[{severity}] {title} - {url}"

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "graphql-cop",
                str(finding.get("rule_id", "")),
                str(finding.get("url", "")),
            ]
        )

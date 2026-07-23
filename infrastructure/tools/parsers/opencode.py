"""Handler for opencode LLM-based security scan findings."""

import json
from typing import Any, cast

from domain.tools.base import ToolResult

from ._shared import _shared_meta


class OpenCodeScanHandler:
    tool_name = "opencode"
    domain = "llm"
    segment = "llm"
    should_enrich = False
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity", "confidence"})
    normalized_fields: list[str] = [
        "confidence",
        "domain",
        "file_path",
        "finding_type",
        "severity",
        "tool",
    ]
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    enrichment_fields: tuple[Any, ...] | None = None

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = cast(dict[str, Any], result.parsed_data or {})
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        rows: list[dict] = []
        timestamp = ToolResult.now_iso()

        for finding in findings:
            row: dict[str, Any] = {
                "tool": "opencode",
                "domain": "llm",
                "segment": finding.get("segment", "sast"),
                "profile": profile,
                "finding_type": json.dumps(
                    finding.get("finding_type", ["vulnerability"])
                ),
                "severity": finding.get("severity", "medium"),
                "confidence": finding.get("confidence", "probable"),
                "file_path": finding.get("file_path", ""),
                "line_start": finding.get("line_number"),
                "line_end": finding.get("line_number"),
                "description": finding.get("description", ""),
                "rule_id": finding.get("rule_id", ""),
                "cwe": json.dumps(finding.get("cwe", [])),
                "reasoning": finding.get("reasoning", ""),
                "remediation": finding.get("remediation", ""),
                "attack_vector": finding.get("attack_vector", ""),
                "code_snippet": finding.get("code_snippet", ""),
                "triaged_by": "opencode",
                "triaged_at": timestamp,
            }
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        file_info = f"{row.get('file_path', '')}"
        if row.get("line_start"):
            file_info += f":{row['line_start']}"

        parts = [
            "[opencode]",
            row.get("severity", "").upper(),
            "|",
            file_info,
            "|",
            row.get("description", ""),
        ]

        if row.get("rule_id"):
            parts.extend(["|", f"({row['rule_id']})"])

        return " ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "opencode",
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_start", "")),
            ]
        )

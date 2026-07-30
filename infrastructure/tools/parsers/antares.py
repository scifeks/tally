"""Parser and handler for Antares CWE localization output."""

import json
from pathlib import Path
from typing import Any, cast

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

_SEVERITY_MAP: dict[str, str] = {
    "high": "high",
    "medium": "medium",
    "low": "low",
}


def parse_antares_json(json_path: Path) -> dict[str, Any]:
    """Parse an Antares JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return parse_antares_data(data)


def parse_antares_json_string(json_string: str) -> dict[str, Any]:
    """Parse Antares JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {
            "error": f"JSON parse error: {exc}",
            "raw_output": json_string,
        }
    return parse_antares_data(data)


def parse_antares_data(data: dict[str, Any]) -> dict[str, Any]:
    findings = data.get("findings", [])
    parsed_findings = [_parse_finding(f) for f in findings]

    by_severity: dict[str, int] = {}
    files_scanned: set[str] = set()
    for finding in parsed_findings:
        sev = finding["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if finding["file_path"]:
            files_scanned.add(finding["file_path"])

    return {
        "findings": parsed_findings,
        "per_cwe_results": data.get("per_cwe_results", []),
        "summary": {
            "total_findings": len(parsed_findings),
            "by_severity": by_severity,
            "files_scanned": len(files_scanned),
        },
    }


def _parse_finding(finding: dict[str, Any]) -> dict[str, Any]:
    raw_likelihood = finding.get("likelihood_of_exploit", "")
    severity_key = str(raw_likelihood).lower() if raw_likelihood else ""
    severity = _SEVERITY_MAP.get(severity_key, "low")

    raw_cwe = finding.get("cwe_ids", [])
    if isinstance(raw_cwe, str):
        cwe_ids = [raw_cwe]
    elif isinstance(raw_cwe, list):
        cwe_ids = raw_cwe
    else:
        cwe_ids = []

    return {
        "title": finding.get("title", ""),
        "file_path": finding.get("file_path", ""),
        "cwe_ids": cwe_ids,
        "submission_rank": finding.get("submission_rank", 0),
        "likelihood_of_exploit": (str(raw_likelihood) if raw_likelihood else ""),
        "severity": severity,
    }


class AntaresHandler:
    """Handler for Antares CWE localization findings."""

    tool_name = "antares"
    domain = "code"
    segment = "sast"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {"weakness": {"type_weakness"}}
    normalized_fields: list[str] = [
        "confidence",
        "cwe",
        "file_path",
        "finding_type",
        "rule_id",
        "severity",
    ]
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "risk_type",
            ("rule_id", "cwe", "description"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "remediation",
            ("description", "rule_id", "cwe"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "confidence",
            ("confidence", "rule_id", "cwe", "description"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "owasp_name",
            ("cwe", "rule_id", "description"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("rule_id", "description", "file_path", "cwe"),
            PromptStrategy.GENERIC,
        ),
    )

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        """Convert parsed Antares data to normalized finding rows."""
        parsed: dict[str, Any] = cast(dict[str, Any], result.parsed_data or {})
        findings: list[dict[str, Any]] = parsed.get("findings", [])
        per_cwe_results: list[dict[str, Any]] = parsed.get("per_cwe_results", [])
        trace_data: dict[str, dict[str, Any]] = parsed.get("trace_data", {})

        cwe_map: dict[str, dict[str, Any]] = {}
        for cwe_result in per_cwe_results:
            cwe_id = cwe_result.get("cwe_id", "")
            if cwe_id:
                cwe_map[cwe_id] = cwe_result

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            cwe_ids: list[str] = finding.get("cwe_ids", [])
            primary_cwe = cwe_ids[0] if cwe_ids else ""
            severity = finding.get("severity", "low")

            row: dict[str, Any] = {
                "tool": "antares",
                "profile": profile,
                "finding_type": json.dumps(["weakness"]),
                "severity": severity,
                "confidence": "potential",
                "rule_id": primary_cwe,
                "file_path": finding.get("file_path", ""),
                "description": finding.get("title", ""),
                "cwe": json.dumps(cwe_ids),
                "timestamp": timestamp,
                "source_file": source_file,
                "submission_rank": finding.get("submission_rank", 0),
                "likelihood_of_exploit": finding.get("likelihood_of_exploit", ""),
            }

            if primary_cwe in cwe_map:
                cwe_stats = cwe_map[primary_cwe]
                row["cwe_tool_calls"] = cwe_stats.get("tool_call_count", 0)
                row["cwe_duration_seconds"] = cwe_stats.get("duration_seconds", 0.0)

            if primary_cwe in trace_data:
                td = trace_data[primary_cwe]
                row["investigation_trace_summary"] = td.get("summary", "")
                row["investigation_trace_detail"] = td.get("detail", [])

            row.update(_shared_meta(self, "weakness"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        """Render a finding as text for ChromaDB indexing."""
        parts = [
            f"CWE: {row.get('rule_id', '')}",
            f"File: {row.get('file_path', '')}",
            f"Severity: {row.get('severity', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        if row.get("confidence"):
            parts.append(f"Confidence: {row['confidence']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        if row.get("remediation"):
            parts.append(f"Remediation: {row['remediation']}")
        if row.get("risk_type"):
            parts.append(f"Risk type: {row['risk_type']}")
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")

        trace_summary = row.get("investigation_trace_summary")
        if trace_summary:
            parts.append(f"Investigation:\n{trace_summary}")

        return "[antares] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        """Return a deduplication key for a normalized finding."""
        cwe_str = finding.get("cwe", "[]")
        try:
            cwe_list = json.loads(cwe_str) if isinstance(cwe_str, str) else cwe_str
        except json.JSONDecodeError:
            cwe_list = []

        primary_cwe = cwe_list[0] if cwe_list else ""
        file_path = finding.get("file_path", "")

        return "|".join(["antares", str(primary_cwe), str(file_path)])

"""Parser and handler for Antares CWE localization output."""

import json
from pathlib import Path
from typing import Any, cast

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy
from infrastructure.tools.antares_trace import (
    build_trace_detail,
    build_trace_summary,
    parse_trace_file,
)

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
    return _parse_antares_data(data)


def parse_antares_json_string(json_string: str) -> dict[str, Any]:
    """Parse Antares JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_antares_data(data)


def _parse_antares_data(data: dict[str, Any]) -> dict[str, Any]:
    findings = data.get("findings", [])
    parsed_findings = [_parse_finding(f) for f in findings]

    by_severity: dict[str, int] = {}
    files_scanned: set = set()
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
    likelihood = finding.get("likelihood_of_exploit", "Low")
    severity = _SEVERITY_MAP.get(likelihood.lower(), "low")
    cwe_ids = finding.get("cwe_ids", [])
    return {
        "title": finding.get("title", ""),
        "file_path": finding.get("file_path", ""),
        "cwe_ids": cwe_ids,
        "submission_rank": finding.get("submission_rank", 0),
        "likelihood_of_exploit": likelihood,
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
        trace_map: dict[str, Path] = parsed.get("trace_map", {})

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
            title = finding.get("title", "")
            file_path = finding.get("file_path", "")
            submission_rank = finding.get("submission_rank", 0)
            likelihood = finding.get("likelihood_of_exploit", "")

            meta_dict: dict[str, Any] = {
                "submission_rank": submission_rank,
                "likelihood_of_exploit": likelihood,
            }
            if primary_cwe in cwe_map:
                cwe_stats = cwe_map[primary_cwe]
                meta_dict["cwe_tool_calls"] = cwe_stats.get("tool_call_count", 0)
                meta_dict["cwe_duration_seconds"] = cwe_stats.get(
                    "duration_seconds", 0.0
                )

            if primary_cwe in trace_map:
                trace_path = trace_map[primary_cwe]
                events = parse_trace_file(trace_path)
                trace_summary = build_trace_summary(events)
                trace_detail = build_trace_detail(events)
                meta_dict["investigation_trace_summary"] = trace_summary
                meta_dict["investigation_trace_detail"] = trace_detail

            row: dict[str, Any] = {
                "tool": "antares",
                "profile": profile,
                "finding_type": json.dumps(["weakness"]),
                "severity": severity,
                "confidence": "potential",
                "rule_id": primary_cwe,
                "file_path": file_path,
                "description": title,
                "cwe": json.dumps(cwe_ids),
                "timestamp": timestamp,
                "source_file": source_file,
                "meta": json.dumps(meta_dict),
            }

            row.update(_shared_meta(self, "weakness"))

            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        """Render a row as a human-readable string for ChromaDB indexing."""
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

        meta_str = row.get("meta", "{}")
        try:
            meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            trace_summary = meta.get("investigation_trace_summary")
            if trace_summary:
                parts.append(f"Investigation:\n{trace_summary}")
        except (json.JSONDecodeError, ValueError):
            pass

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

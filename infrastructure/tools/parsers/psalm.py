"""Parser for Psalm taint analysis SARIF output."""

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

_CWE_MAP: dict[str, str] = {
    "TaintedSql": "CWE-89",
    "TaintedHtml": "CWE-79",
    "TaintedShell": "CWE-78",
    "TaintedInclude": "CWE-98",
    "TaintedEval": "CWE-95",
    "TaintedSSRF": "CWE-918",
    "TaintedFile": "CWE-73",
    "TaintedHeader": "CWE-113",
    "TaintedLdap": "CWE-90",
    "TaintedUnserialize": "CWE-502",
    "TaintedCallable": "CWE-470",
    "TaintedCookie": "CWE-614",
    "TaintedUserSecret": "CWE-200",
    "TaintedSystemSecret": "CWE-200",
}

_SEVERITY_MAP: dict[str, str] = {
    "error": "high",
    "warning": "medium",
    "note": "low",
}


def parse_psalm_sarif(sarif_path: Path) -> dict[str, Any]:
    """Parse a Psalm SARIF output file into structured data."""
    try:
        with open(sarif_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_sarif_data(data)


def parse_psalm_sarif_string(sarif_string: str) -> dict[str, Any]:
    """Parse Psalm SARIF from a raw string into structured data."""
    try:
        data = json.loads(sarif_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": sarif_string}
    return _parse_sarif_data(data)


def _parse_sarif_data(data: dict[str, Any]) -> dict[str, Any]:
    runs = data.get("runs", [])
    if not runs:
        return {
            "findings": [],
            "summary": {"total_findings": 0, "by_severity": {}},
        }

    results = runs[0].get("results", [])
    findings = [_parse_finding(r) for r in results if _is_taint_result(r)]

    by_severity: dict[str, int] = {}
    for finding in findings:
        sev = finding["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings), "by_severity": by_severity},
    }


def _is_taint_result(result: dict[str, Any]) -> bool:
    rule_id = result.get("ruleId", "")
    return rule_id.startswith("Tainted")


def _parse_finding(result: dict[str, Any]) -> dict[str, Any]:
    rule_id = result.get("ruleId", "")
    level = result.get("level", "error")
    message_text = _extract_message(result)
    location_data = _extract_location(result)
    taint_flow_data = _extract_taint_flow(result)

    return {
        "rule_id": rule_id,
        "severity": _SEVERITY_MAP.get(level, "high"),
        "message": message_text,
        "file_path": location_data["file_path"],
        "line_start": location_data["line_start"],
        "col_start": location_data["col_start"],
        "line_end": location_data["line_end"],
        "cwe": _CWE_MAP.get(rule_id, ""),
        "confidence": "confirmed",
        "taint_flow": taint_flow_data["flow"],
        "taint_source": taint_flow_data["source"],
        "taint_sink": taint_flow_data["sink"],
        "taint_type": rule_id.removeprefix("Tainted").lower(),
    }


def _extract_message(result: dict[str, Any]) -> str:
    message_obj = result.get("message", {})
    return message_obj.get("text", "") if isinstance(message_obj, dict) else ""


def _extract_location(result: dict[str, Any]) -> dict[str, Any]:
    locations = result.get("locations", [])
    if not locations:
        return {
            "file_path": "",
            "line_start": 0,
            "col_start": None,
            "line_end": None,
        }

    loc = locations[0]
    phys_loc = loc.get("physicalLocation", {})
    artifact_loc = phys_loc.get("artifactLocation", {})
    region = phys_loc.get("region", {})

    return {
        "file_path": artifact_loc.get("uri", ""),
        "line_start": region.get("startLine", 0),
        "col_start": region.get("startColumn"),
        "line_end": region.get("endLine"),
    }


def _extract_taint_flow(result: dict[str, Any]) -> dict[str, Any]:
    code_flows = result.get("codeFlows", [])
    if not code_flows:
        return {"flow": [], "source": "", "sink": ""}

    flow_steps = []
    flow_list = code_flows[0].get("threadFlows", [])
    if flow_list:
        thread_locations = flow_list[0].get("locations", [])
        for step in thread_locations:
            loc_data = step.get("location", {})
            phys_loc = loc_data.get("physicalLocation", {})
            artifact_loc = phys_loc.get("artifactLocation", {})
            region = phys_loc.get("region", {})
            msg = loc_data.get("message", {})

            flow_step = {
                "file": artifact_loc.get("uri", ""),
                "line": region.get("startLine", 0),
                "text": msg.get("text", "") if isinstance(msg, dict) else "",
            }
            flow_steps.append(flow_step)

    source_text = ""
    sink_text = ""
    if flow_steps:
        source_text = flow_steps[0].get("text", "")
        sink_text = flow_steps[-1].get("text", "")

    return {"flow": flow_steps, "source": source_text, "sink": sink_text}


class PsalmHandler:
    tool_name = "psalm"
    domain = "code"
    segment = "sast"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability", "type_weakness"}
    }
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
            ("rule_id", "cwe", "description", "taint_type"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "remediation",
            ("description", "rule_id", "cwe", "taint_source", "taint_sink"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "owasp_name",
            ("cwe", "rule_id", "description", "taint_type"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("rule_id", "description", "file_path", "cwe"),
            PromptStrategy.GENERIC,
        ),
    )

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            rule_id = finding.get("rule_id", "")
            severity = finding.get("severity", "high")
            message = finding.get("message", "")
            file_path = finding.get("file_path", "")
            line_start = finding.get("line_start", 0)
            line_end = finding.get("line_end")
            col_start = finding.get("col_start")
            cwe = finding.get("cwe") or ""
            confidence = finding.get("confidence") or ""
            taint_flow = finding.get("taint_flow") or []
            taint_source = finding.get("taint_source") or ""
            taint_sink = finding.get("taint_sink") or ""
            taint_type = finding.get("taint_type") or ""

            row: dict[str, Any] = {
                "tool": "psalm",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": severity,
                "rule_id": rule_id,
                "file_path": file_path,
                "line_start": line_start,
                "description": message,
                "confidence": confidence,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if line_end is not None:
                row["line_end"] = line_end
            if col_start is not None:
                row["col_start"] = col_start
            if cwe:
                row["cwe"] = cwe
            if taint_flow:
                row["taint_flow"] = taint_flow
            if taint_source:
                row["taint_source"] = taint_source
            if taint_sink:
                row["taint_sink"] = taint_sink
            if taint_type:
                row["taint_type"] = taint_type
            if rule_id:
                row["title"] = rule_id

            row.update(_shared_meta(self, "vulnerability"))

            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Rule: {row.get('rule_id', '')}",
            f"File: {row.get('file_path', '')}:{row.get('line_start', '')}",
            f"Severity: {row.get('severity', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        if row.get("cwe"):
            parts.append(f"CWE: {row['cwe']}")
        if row.get("confidence"):
            parts.append(f"Confidence: {row['confidence']}")
        if row.get("taint_source"):
            parts.append(f"Taint source: {row['taint_source']}")
        if row.get("taint_sink"):
            parts.append(f"Taint sink: {row['taint_sink']}")
        return "[psalm] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "psalm",
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_start", "")),
            ]
        )

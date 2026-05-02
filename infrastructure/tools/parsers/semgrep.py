"""Parser and handler for semgrep SAST output."""

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import OWASP_CODE_TO_NAME
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

_SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}

_CONFIDENCE_MAP: dict[str, str] = {
    "high": "confirmed",
    "medium": "probable",
    "low": "potential",
}


# Parse functions (called by BaseSemgrepTool.parse_output)


def parse_semgrep_json(json_path: Path) -> dict[str, Any]:
    """Parse a semgrep JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_semgrep_data(data)


def parse_semgrep_json_string(json_string: str) -> dict[str, Any]:
    """Parse semgrep JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_semgrep_data(data)


# Internal parse helpers


def _parse_semgrep_data(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    findings = [_parse_finding(r) for r in results]

    by_severity: dict[str, int] = {}
    files_scanned: set = set()
    for finding in findings:
        sev = finding["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if finding["file_path"]:
            files_scanned.add(finding["file_path"])

    return {
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "files_scanned": len(files_scanned),
        },
    }


def _parse_finding(result: dict[str, Any]) -> dict[str, Any]:
    extra = result.get("extra", {})
    start = result.get("start", {})
    end = result.get("end", {})
    metadata = _extract_metadata(extra)
    return {
        "rule_id": result.get("check_id", ""),
        "severity": _extract_severity(extra),
        "message": extra.get("message", ""),
        "file_path": result.get("path", ""),
        "line_start": start.get("line", 0),
        "col_start": start.get("col"),
        "line_end": end.get("line", 0),
        "col_end": end.get("col"),
        "code_snippet": extra.get("lines", ""),
        "fix": extra.get("fix"),
        "fingerprint": extra.get("fingerprint"),
        "cwe": metadata["cwe"],
        "owasp": metadata["owasp"],
        "confidence": metadata["confidence"],
        "category": metadata["category"],
        "technology": metadata["technology"],
        "subcategory": metadata["subcategory"],
        "likelihood": metadata["likelihood"],
        "impact": metadata["impact"],
        "references": metadata["references"],
    }


def _extract_severity(extra: dict[str, Any]) -> str:
    raw = extra.get("severity", "INFO").upper()
    return _SEVERITY_MAP.get(raw, "low")


def _extract_metadata(extra: dict[str, Any]) -> dict[str, Any]:
    meta = extra.get("metadata", {})
    raw_conf = meta.get("confidence")
    confidence = (
        _CONFIDENCE_MAP.get(raw_conf.lower()) if isinstance(raw_conf, str) else None
    )

    technology = meta.get("technology")
    subcategory = meta.get("subcategory")
    references = meta.get("references")

    return {
        "cwe": meta.get("cwe"),
        "owasp": meta.get("owasp"),
        "confidence": confidence,
        "category": meta.get("category"),
        "technology": technology if isinstance(technology, list) else None,
        "subcategory": subcategory if isinstance(subcategory, list) else None,
        "likelihood": meta.get("likelihood"),
        "impact": meta.get("impact"),
        "references": references if isinstance(references, list) else None,
    }


# Handler (normalize → SQLite rows, render → ChromaDB text)


class SemgrepHandler:
    tool_name = "semgrep"
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
            ("rule_id", "cwe", "owasp", "description", "category"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "remediation",
            ("description", "rule_id", "cwe", "category", "fix"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "confidence",
            ("confidence", "subcategory", "likelihood", "rule_id"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "owasp_name",
            ("owasp", "cwe", "rule_id", "description", "category"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("rule_id", "description", "file_path", "cwe", "category"),
            PromptStrategy.GENERIC,
        ),
    )

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            rule_id = finding.get("rule_id", "")
            severity = finding.get("severity", "low")
            message = finding.get("message", "")
            file_path = finding.get("file_path", "")
            line_start = finding.get("line_start", 0)
            col_start = finding.get("col_start")
            line_end = finding.get("line_end", 0)
            col_end = finding.get("col_end")
            fix = finding.get("fix")
            fingerprint = finding.get("fingerprint")
            cwe = finding.get("cwe") or ""
            owasp = finding.get("owasp") or ""
            confidence = finding.get("confidence") or ""
            category = finding.get("category") or ""
            technology: list[str] = finding.get("technology") or []
            subcategory: list[str] = finding.get("subcategory") or []
            likelihood = finding.get("likelihood") or ""
            impact = finding.get("impact") or ""
            references: list[str] = finding.get("references") or []

            row: dict[str, Any] = {
                "tool": "semgrep",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": severity,
                "rule_id": rule_id,
                "file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "description": message,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if col_start is not None:
                row["col_start"] = col_start
            if col_end is not None:
                row["col_end"] = col_end
            if cwe:
                row["cwe"] = cwe
            if owasp:
                row["owasp"] = owasp
                raw_list: list = owasp if isinstance(owasp, list) else [owasp]
                names: list[str] = []
                for entry in raw_list:
                    code = str(entry).split(" ")[0].strip()
                    name = OWASP_CODE_TO_NAME.get(code)
                    if name:
                        names.append(name)
                if names:
                    row["owasp_name"] = json.dumps(list(dict.fromkeys(names)))
            if confidence:
                row["confidence"] = confidence
            if fix:
                row["fix"] = fix
            if fingerprint:
                row["fingerprint"] = fingerprint
            if category:
                row["category"] = category
            if technology:
                row["technology"] = ", ".join(technology)
            if subcategory:
                row["subcategory"] = ", ".join(subcategory)
            if likelihood:
                row["likelihood"] = likelihood
            if impact:
                row["impact"] = impact
            if references:
                row["references"] = ", ".join(references)
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
        if row.get("owasp"):
            parts.append(f"OWASP: {row['owasp']}")
        if row.get("confidence"):
            parts.append(f"Confidence: {row['confidence']}")
        if row.get("category"):
            parts.append(f"Category: {row['category']}")
        if row.get("risk_type"):
            parts.append(f"Risk type: {row['risk_type']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        if row.get("remediation"):
            parts.append(f"Remediation: {row['remediation']}")
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")
        if row.get("references"):
            parts.append(f"References: {row['references']}")
        return "[semgrep] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "semgrep",
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_start", "")),
            ]
        )

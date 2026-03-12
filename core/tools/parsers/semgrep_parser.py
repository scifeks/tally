import json
from pathlib import Path
from typing import Any

_SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
    confidence = raw_conf.lower() if isinstance(raw_conf, str) else None

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

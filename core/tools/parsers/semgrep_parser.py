import json
from pathlib import Path
from typing import Any, Dict, Optional

_SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


def parse_semgrep_json(json_path: Path) -> Dict[str, Any]:
    """Parse a semgrep JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_semgrep_data(data)


def parse_semgrep_json_string(json_string: str) -> Dict[str, Any]:
    """Parse semgrep JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_semgrep_data(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_semgrep_data(data: Dict[str, Any]) -> Dict[str, Any]:
    results = data.get("results", [])
    findings = [_parse_finding(r) for r in results]

    by_severity: Dict[str, int] = {}
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


def _parse_finding(result: Dict[str, Any]) -> Dict[str, Any]:
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
        "line_end": end.get("line", 0),
        "code_snippet": extra.get("lines", ""),
        "cwe": metadata["cwe"],
        "owasp": metadata["owasp"],
    }


def _extract_severity(extra: Dict[str, Any]) -> str:
    raw = extra.get("severity", "INFO").upper()
    return _SEVERITY_MAP.get(raw, "low")


def _extract_metadata(extra: Dict[str, Any]) -> Dict[str, Optional[str]]:
    meta = extra.get("metadata", {})
    return {
        "cwe": meta.get("cwe"),
        "owasp": meta.get("owasp"),
    }

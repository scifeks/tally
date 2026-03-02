"""Parser for gitleaks JSON secret-detection output."""
import json
from pathlib import Path
from typing import Any, Dict, List, Set


def parse_gitleaks_json(json_path: Path) -> Dict[str, Any]:
    """Parse a gitleaks JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_gitleaks_data(data)


def parse_gitleaks_json_string(json_string: str) -> Dict[str, Any]:
    """Parse gitleaks JSON from a raw string into structured data."""
    stripped = json_string.strip() if json_string else ""
    if not stripped:
        # gitleaks outputs nothing when no secrets found
        return _parse_gitleaks_data([])
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_gitleaks_data(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_gitleaks_data(findings: Any) -> Dict[str, Any]:
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        return {"error": "Unexpected gitleaks output format (expected JSON array)"}

    secrets = [_parse_secret(f) for f in findings]

    by_rule: Dict[str, int] = {}
    files_with_secrets: Set[str] = set()
    for secret in secrets:
        rule = secret["rule_id"]
        by_rule[rule] = by_rule.get(rule, 0) + 1
        if secret["file_path"]:
            files_with_secrets.add(secret["file_path"])

    return {
        "secrets": secrets,
        "summary": {
            "total_secrets": len(secrets),
            "by_rule": by_rule,
            "files_with_secrets": len(files_with_secrets),
        },
    }


def _parse_secret(finding: Dict[str, Any]) -> Dict[str, Any]:
    raw_secret = finding.get("Secret", "")
    tags: List[str] = finding.get("Tags") or []
    commit = finding.get("Commit") or None
    return {
        "rule_id": finding.get("RuleID", ""),
        "description": finding.get("Description", ""),
        "file_path": finding.get("File", ""),
        "line_number": finding.get("StartLine", 0),
        "commit": commit,
        "secret": _redact_secret(raw_secret),
        "match": finding.get("Match", ""),
        "tags": tags,
    }


def _redact_secret(secret: str) -> str:
    """Mask secret value, showing only the first 4 characters."""
    if not secret:
        return "****"
    if len(secret) < 10:
        return "****"
    return secret[:4] + "****"

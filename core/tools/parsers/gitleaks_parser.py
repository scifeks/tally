"""Parser for gitleaks JSON secret-detection output."""

import json
from pathlib import Path
from typing import Any


def parse_gitleaks_json(json_path: Path) -> dict[str, Any]:
    """Parse a gitleaks JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_gitleaks_data(data)


def parse_gitleaks_json_string(json_string: str) -> dict[str, Any]:
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


def _parse_gitleaks_data(findings: Any) -> dict[str, Any]:
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        return {"error": "Unexpected gitleaks output format (expected JSON array)"}

    secrets = [_parse_secret(f) for f in findings]

    by_rule: dict[str, int] = {}
    files_with_secrets: set[str] = set()
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


def _parse_secret(finding: dict[str, Any]) -> dict[str, Any]:
    raw_secret = finding.get("Secret", "")
    tags: list[str] = finding.get("Tags") or []
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


def combine_gitleaks_results(dir_data: dict, git_data: dict) -> dict[str, Any]:
    """Merge dir-scan and git-scan results into a single combined result.

    The returned dict has top-level ``secrets`` and ``summary`` keys consumed
    by the ingestor, plus ``dir`` / ``git`` sub-keys preserving each scan's
    individual data.
    """
    dir_secrets: list[dict] = (dir_data or {}).get("secrets", [])
    git_secrets: list[dict] = (git_data or {}).get("secrets", [])

    # Deduplicate by (rule_id, file_path, line_number, commit)
    seen: set[tuple] = set()
    merged: list[dict] = []
    for secret in dir_secrets + git_secrets:
        key = (
            secret.get("rule_id", ""),
            secret.get("file_path", ""),
            secret.get("line_number", 0),
            secret.get("commit"),
        )
        if key not in seen:
            seen.add(key)
            merged.append(secret)

    by_rule: dict[str, int] = {}
    files_with_secrets: set[str] = set()
    for secret in merged:
        rule = secret.get("rule_id", "")
        by_rule[rule] = by_rule.get(rule, 0) + 1
        if secret.get("file_path"):
            files_with_secrets.add(secret["file_path"])

    combined_summary = {
        "total_secrets": len(merged),
        "by_rule": by_rule,
        "files_with_secrets": len(files_with_secrets),
    }

    return {
        "dir": dir_data,
        "git": git_data,
        "secrets": merged,
        "summary": combined_summary,
    }


def _redact_secret(secret: str) -> str:
    """Mask secret value, showing only the first 4 characters."""
    if not secret:
        return "****"
    if len(secret) < 10:
        return "****"
    return secret[:4] + "****"

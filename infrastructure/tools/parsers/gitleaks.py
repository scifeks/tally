"""Parser and handler for gitleaks secret-detection output."""

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import CONFIDENCE_CONFIRMED, SEVERITY_HIGH

from ._shared import _first_output_file, _shared_meta

# Parse functions (called by BaseGitleaksTool.parse_output)


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


# Internal parse helpers


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
    tags: list[str] = finding.get("Tags") or []
    commit = finding.get("Commit") or None
    symlink_file = finding.get("SymlinkFile") or None
    return {
        "rule_id": finding.get("RuleID", ""),
        "description": finding.get("Description", ""),
        "file_path": finding.get("File", ""),
        "line_number": finding.get("StartLine", 0),
        "end_line": finding.get("EndLine", 0),
        "start_column": finding.get("StartColumn", 0),
        "end_column": finding.get("EndColumn", 0),
        "entropy": finding.get("Entropy"),
        "author": finding.get("Author", ""),
        "email": finding.get("Email", ""),
        "date": finding.get("Date", ""),
        "message": finding.get("Message", ""),
        "commit": commit,
        "symlink_file": symlink_file,
        "tags": tags,
        "fingerprint": finding.get("Fingerprint", ""),
    }


def combine_gitleaks_results(dir_data: dict, git_data: dict) -> dict[str, Any]:
    """Merge dir-scan and git-scan results into a single combined result.

    The returned dict has top-level ``secrets`` and ``summary`` keys consumed
    by the ingestor, plus ``dir`` / ``git`` sub-keys preserving each scan's
    individual data.
    """
    dir_secrets: list[dict] = (dir_data or {}).get("secrets", [])
    git_secrets: list[dict] = (git_data or {}).get("secrets", [])

    for s in dir_secrets:
        s["source"] = "dir"
    for s in git_secrets:
        s.setdefault("source", "git")

    # Deduplicate by (rule_id, file_path, line_number).  commit is intentionally
    # excluded: the same secret found by both a dir scan (commit=None) and a git
    # scan (commit=hash) is the same logical finding and should appear only once.
    seen: set[tuple] = set()
    merged: list[dict] = []
    for secret in dir_secrets + git_secrets:
        key = (
            secret.get("rule_id", ""),
            secret.get("file_path", ""),
            secret.get("line_number", 0),
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


# Handler (normalize → SQLite rows, render → ChromaDB text)


class GitleaksHandler:
    tool_name = "gitleaks"
    domain = "code"
    segment = "secrets"
    should_enrich = False
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "risk_type", "confidence"}
    )
    type_flags: dict[str, set[str]] = {"secret": {"type_secret"}}
    enrichment_fields = None
    normalized_fields: list[str] = [
        "confidence",
        "domain",
        "file_path",
        "finding_type",
        "severity",
        "tool",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        secrets: list[dict[str, Any]] = parsed.get("secrets", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for secret in secrets:
            rule_id = secret.get("rule_id", "")
            description = secret.get("description", "")
            file_path = secret.get("file_path", "")
            line_number = secret.get("line_number", 0)
            end_line = secret.get("end_line", 0)
            start_column = secret.get("start_column", 0)
            end_column = secret.get("end_column", 0)
            entropy = secret.get("entropy")
            author = secret.get("author", "")
            email = secret.get("email", "")
            date = secret.get("date", "")
            message = secret.get("message", "")
            commit = secret.get("commit")
            symlink_file = secret.get("symlink_file")
            tags: list[str] = secret.get("tags") or []
            fingerprint = secret.get("fingerprint", "")
            source = secret.get("source", "")

            tags_str = ", ".join(tags) if tags else ""

            row: dict[str, Any] = {
                "tool": "gitleaks",
                "profile": profile,
                "finding_type": json.dumps(["secret"]),
                "severity": SEVERITY_HIGH,
                "confidence": CONFIDENCE_CONFIRMED,
                "rule_id": rule_id,
                "file_path": file_path,
                "line_number": line_number,
                "tags": tags_str,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if description:
                row["description"] = description
            if rule_id:
                row["risk_type"] = rule_id
            if end_line:
                row["end_line"] = end_line
            if start_column:
                row["start_column"] = start_column
            if end_column:
                row["end_column"] = end_column
            if entropy is not None:
                row["entropy"] = entropy
            if author:
                row["author"] = author
            if email:
                row["email"] = email
            if date:
                row["date"] = date
            if message:
                row["message"] = message
            if commit:
                row["commit"] = commit
            if symlink_file:
                row["symlink_file"] = symlink_file
            if fingerprint:
                row["fingerprint"] = fingerprint
            if source:
                row["source"] = source
            if rule_id:
                row["title"] = rule_id
            row.update(_shared_meta(self, "secret"))

            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Rule: {row.get('rule_id', '')}",
            f"File: {row.get('file_path', '')}:{row.get('line_number', '')}",
            f"Secret type: {row.get('description', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
        ]
        if row.get("tags"):
            parts.append(f"Tags: {row['tags']}")
        if row.get("author"):
            parts.append(f"Author: {row['author']}")
        if row.get("commit"):
            parts.append(f"Commit: {row['commit']}")
        if row.get("source"):
            parts.append(f"Source: {row['source']}")
        if row.get("date"):
            parts.append(f"Date: {row['date']}")
        return "[gitleaks] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "gitleaks",
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_number", "")),
            ]
        )

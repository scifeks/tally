"""GitleaksHandler — converts gitleaks ToolResult into normalized finding dicts."""

import json
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import CONFIDENCE_CONFIRMED, SEVERITY_HIGH

from ._shared import _first_output_file, _shared_meta


class GitleaksHandler:
    tool_name = "gitleaks"
    domain = "code"
    segment = "secrets"
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "risk_type", "confidence"}
    )
    type_flags: dict[str, set[str]] = {"secret": {"type_secret"}}
    should_enrich = False
    enrichment_fields = None

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
        if row.get("date"):
            parts.append(f"Date: {row['date']}")
        return "[gitleaks] " + " | ".join(parts)

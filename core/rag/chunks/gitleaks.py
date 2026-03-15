"""GitleaksChunkBuilder — converts gitleaks ToolResult into ChromaDB document chunks."""

import json
from datetime import UTC, datetime
from typing import Any

from core.tools.base import ToolResult
from core.tools.constants import CONFIDENCE_CONFIRMED, SEVERITY_HIGH

from ._shared import _first_output_file, _shared_meta


class GitleaksChunkBuilder:
    tool_name = "gitleaks"

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        secrets: list[dict[str, Any]] = parsed.get("secrets", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for si, secret in enumerate(secrets):
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

            text = (
                f"[gitleaks] Secret detected: {rule_id} in {file_path}:{line_number}\n"
                f"Type: {description}\n"
                f"Tags: {tags_str}\n"
                "Note: Secret value redacted"
            )

            meta: dict[str, Any] = {
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
                meta["description"] = description
            if rule_id:
                meta["risk_type"] = rule_id
            if end_line:
                meta["end_line"] = end_line
            if start_column:
                meta["start_column"] = start_column
            if end_column:
                meta["end_column"] = end_column
            if entropy is not None:
                meta["entropy"] = entropy
            if author:
                meta["author"] = author
            if email:
                meta["email"] = email
            if date:
                meta["date"] = date
            if message:
                meta["message"] = message
            if commit:
                meta["commit"] = commit
            if symlink_file:
                meta["symlink_file"] = symlink_file
            if fingerprint:
                meta["fingerprint"] = fingerprint
            meta.update(_shared_meta("gitleaks", "secret"))

            doc_id = f"gitleaks_{profile}_secret_{si}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "gitleaks",
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_number", "")),
            ]
        )

"""SemgrepChunkBuilder — converts semgrep ToolResult into ChromaDB document chunks."""

import json
from datetime import UTC, datetime
from typing import Any

from domain.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta


class SemgrepChunkBuilder:
    tool_name = "semgrep"
    domain = "code"
    segment = "sast"
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability", "type_weakness"}
    }

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for fi, finding in enumerate(findings):
            rule_id = finding.get("rule_id", "")
            severity = finding.get("severity", "low")
            message = finding.get("message", "")
            file_path = finding.get("file_path", "")
            line_start = finding.get("line_start", 0)
            col_start = finding.get("col_start")
            line_end = finding.get("line_end", 0)
            col_end = finding.get("col_end")
            code_snippet = finding.get("code_snippet", "")
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

            text = (
                f"[semgrep] [{severity.upper()}] {rule_id} "
                f"in {file_path}:{line_start}\n"
                f"Message: {message}\n"
                f"Code: {code_snippet}"
            )

            meta: dict[str, Any] = {
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
                meta["col_start"] = col_start
            if col_end is not None:
                meta["col_end"] = col_end
            if cwe:
                meta["cwe"] = cwe
            if owasp:
                meta["owasp"] = owasp
            if confidence:
                meta["confidence"] = confidence
            if fix:
                meta["fix"] = fix
            if fingerprint:
                meta["fingerprint"] = fingerprint
            if category:
                meta["category"] = category
            if technology:
                meta["technology"] = ", ".join(technology)
            if subcategory:
                meta["subcategory"] = ", ".join(subcategory)
            if likelihood:
                meta["likelihood"] = likelihood
            if impact:
                meta["impact"] = impact
            if references:
                meta["references"] = ", ".join(references)
            meta.update(_shared_meta(self, "vulnerability"))

            doc_id = f"semgrep_{profile}_finding_{fi}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "semgrep",
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_start", "")),
            ]
        )

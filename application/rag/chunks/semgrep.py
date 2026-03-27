"""SemgrepHandler — converts semgrep ToolResult into normalized finding dicts."""

import json
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import OWASP_CODE_TO_NAME
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta


class SemgrepHandler:
    tool_name = "semgrep"
    domain = "code"
    segment = "sast"
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability", "type_weakness"}
    }
    # Per-field enrichment spec: each entry declares which metadata keys to send
    # to the LLM and which prompt strategy to use. description is omitted because
    # semgrep always sets it from the rule message; no LLM call is needed.
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

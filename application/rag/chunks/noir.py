"""NoirHandler — converts Noir ToolResult into normalised endpoint records.

Noir is an endpoint-discovery tool, not a vulnerability scanner.  Its
findings are stored as ``informational`` records so that downstream steps
(ChromaDB RAG, triage) can see the application's attack surface without
mistaking endpoint metadata for exploitable vulnerabilities.

Following ADR-009 (nmap informational type), ``type_flags`` uses an empty
set so all ``type_*`` boolean columns remain ``False``; the ``finding_type``
JSON field is the canonical classification.

``should_enrich = False`` because LLM enrichment adds no value to raw
endpoint metadata.
"""

from __future__ import annotations

import json
from typing import Any

from domain.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta


class NoirHandler:
    """Normalise and render Noir endpoint-discovery output."""

    tool_name = "noir"
    domain = "web"
    segment = "api"
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "description"}
    )
    # Empty set → all type_* columns are False (see ADR-009 rationale).
    type_flags: dict[str, set[str]] = {"informational": set()}
    should_enrich = False
    enrichment_fields = None

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        """Convert Noir ToolResult into one SQLite row per endpoint+method."""
        parsed: dict[str, Any] = result.parsed_data or {}
        endpoints: list[dict[str, Any]] = parsed.get("endpoints", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        rows: list[dict] = []

        for endpoint in endpoints:
            path: str = endpoint.get("path") or ""
            method: str = endpoint.get("method") or ""

            all_params: list[dict[str, Any]] = (
                endpoint.get("path_params", [])
                + endpoint.get("query_params", [])
                + endpoint.get("header_params", [])
                + endpoint.get("cookie_params", [])
                + endpoint.get("body_params", [])
            )
            param_names = [str(p.get("name", "")) for p in all_params if p.get("name")]

            description = f"Endpoint {method} {path}"
            if param_names:
                description += f" — params: {', '.join(param_names)}"

            row: dict[str, Any] = {
                "tool": "noir",
                "profile": profile,
                "finding_type": json.dumps(["informational"]),
                "severity": "informational",
                "confidence": "confirmed",
                "risk_type": "endpoint-discovery",
                "url": path,
                "method": method,
                "description": description,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            row.update(_shared_meta(self, "informational"))
            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        """Render a normalised endpoint row as ChromaDB document text."""
        parts = [
            f"Method: {row.get('method', '')}",
            f"Path: {row.get('url', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        if row.get("profile"):
            parts.append(f"Profile: {row['profile']}")
        return "[noir] " + " | ".join(parts)

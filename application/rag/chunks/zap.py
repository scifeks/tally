"""ZapHandler — converts ZAP ToolResult into normalized finding dicts."""

import json
import logging
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import CONFIDENCE_CONFIRMED
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta

logger = logging.getLogger(__name__)

# Alerts whose description starts with this prefix are ZAP self-diagnostics, not
# application findings. Suppress them before they enter the ingest pipeline.
_ZAP_VERSION_ALERT_PREFIX = (
    "The version of ZAP you are using to test your app is out of date"
)


class ZapHandler:
    tool_name = "zap"
    domain = "web"
    segment = "api"
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "remediation", "description"}
    )
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    # risk_type is already in metadata as alert_name so the metadata check filters
    # it out before any LLM call. Only owasp_name needs dedicated enrichment.
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("alert_name", "description", "cwe_id", "param", "evidence"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("alert_name", "url", "description", "param"),
            PromptStrategy.GENERIC,
        ),
    )

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        alerts: list[dict[str, Any]] = parsed.get("alerts", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for alert in alerts:
            description = alert.get("description", "")
            if description.startswith(_ZAP_VERSION_ALERT_PREFIX):
                logger.debug("Skipping ZAP self-diagnostic alert: %s", description[:80])
                continue

            alert_name = alert.get("alert_name", "")
            risk = alert.get("risk", "informational")
            raw_confidence = alert.get("confidence", "low")
            url = alert.get("url", "")
            method = alert.get("method", "")
            param = alert.get("param") or ""
            solution = alert.get("solution", "")
            cwe_id = alert.get("cwe_id")

            # Map ZAP confidence (text or integer string) to our constants
            _ZAP_CONFIDENCE: dict[str, str] = {
                "confirmed": CONFIDENCE_CONFIRMED,
                "4": CONFIDENCE_CONFIRMED,
                "high": "probable",
                "3": "probable",
                "medium": "probable",
                "2": "probable",
                "low": "potential",
                "1": "potential",
                "false positive": "potential",
                "0": "potential",
            }
            confidence = _ZAP_CONFIDENCE.get(str(raw_confidence).lower(), "potential")

            row: dict[str, Any] = {
                "tool": "zap",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": risk,
                "confidence": confidence,
                "risk_type": alert_name,
                "alert_name": alert_name,
                "url": url,
                "method": method.upper(),
                "description": description,
                "remediation": solution,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            evidence = alert.get("evidence") or ""
            if param:
                row["param"] = param
            if evidence:
                row["evidence"] = evidence
            if cwe_id is not None and cwe_id > 0:
                row["cwe_id"] = cwe_id
            row.update(_shared_meta(self, "vulnerability"))

            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Alert: {row.get('alert_name', '')}",
            f"URL: {row.get('url', '')}",
            f"Method: {row.get('method', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        if row.get("remediation"):
            parts.append(f"Remediation: {row['remediation']}")
        if row.get("cwe_id"):
            parts.append(f"CWE: {row['cwe_id']}")
        if row.get("param"):
            parts.append(f"Parameter: {row['param']}")
        if row.get("evidence"):
            parts.append(f"Evidence: {row['evidence']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        if row.get("owasp_name"):
            parts.append(f"OWASP category: {row['owasp_name']}")
        return "[zap] " + " | ".join(parts)

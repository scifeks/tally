"""ZapChunkBuilder — converts ZAP ToolResult into ChromaDB document chunks."""

import json
import logging
from datetime import UTC, datetime
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


class ZapChunkBuilder:
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
    )

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        alerts: list[dict[str, Any]] = parsed.get("alerts", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for ai, alert in enumerate(alerts):
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
            evidence = alert.get("evidence") or ""
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

            text_lines = [
                f"[zap] [{risk.upper()}] API vulnerability: {alert_name}",
                f"Endpoint: {method} {url}",
            ]
            if param:
                text_lines.append(f"Parameter: {param}")
            text_lines.append(f"Description: {description}")
            if evidence:
                text_lines.append(f"Evidence: {evidence}")
            text_lines.append(f"Solution: {solution}")
            text = "\n".join(text_lines)

            meta: dict[str, Any] = {
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
            if param:
                meta["param"] = param
            if cwe_id is not None and cwe_id > 0:
                meta["cwe_id"] = cwe_id
            meta.update(_shared_meta(self, "vulnerability"))

            doc_id = f"zap_{profile}_alert_{ai}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "zap",
                str(finding.get("url", "")),
                str(finding.get("method", "")),
                str(finding.get("alert_name", "")),
            ]
        )

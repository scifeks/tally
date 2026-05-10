"""Parser and handler for ProjectDiscovery Katana JSONL crawl output.

Katana is a runtime URL-discovery crawler, not a vulnerability scanner.
Its findings are stored as ``informational`` records so that downstream
steps can see the discovered attack surface without confusing endpoint
metadata for exploitable vulnerabilities.

Actual Katana JSONL record schema (verified from katana -j output):
    {
        "timestamp": "...",
        "request": {
            "method": "GET",
            "endpoint": "https://example.com/path?q=1",
            "raw": "GET /path HTTP/1.1\\r\\n..."
        },
        "response": {
            "status_code": 200,
            "headers": {"content-type": "text/html", ...},
            "body": "...",
            "content_length": 528,
            "raw": "..."
        }
    }

``should_enrich = False`` because LLM enrichment adds no value to endpoint
metadata (method + URL is already self-describing).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from domain.tools.base import ToolResult


def parse_katana_jsonl(json_path: Path) -> dict[str, Any]:
    """Parse a Katana JSONL output file into structured endpoint data."""
    try:
        text = json_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "error": f"JSONL read error: {exc}",
            "endpoints": [],
            "summary": {"total_endpoints": 0},
        }
    return parse_katana_jsonl_string(text)


def parse_katana_jsonl_string(jsonl: str) -> dict[str, Any]:
    """Parse Katana JSONL text into structured endpoint data."""
    lines = [ln for ln in jsonl.splitlines() if ln.strip()]
    if not lines:
        return {
            "endpoints": [],
            "summary": {"total_endpoints": 0},
        }

    endpoints: list[dict[str, Any]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        endpoint = _parse_record(record)
        if endpoint is not None:
            endpoints.append(endpoint)

    return {
        "endpoints": endpoints,
        "summary": {"total_endpoints": len(endpoints)},
    }


def _parse_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Extract one endpoint dict from a single Katana JSONL record."""
    request = record.get("request")
    if not isinstance(request, dict):
        return None

    url = request.get("endpoint", "")
    if not url:
        return None

    method = (request.get("method") or "GET").upper()
    parsed = urlparse(url)
    path = parsed.path or "/"

    status_code: int = 0
    content_type: str | None = None
    response = record.get("response")
    if isinstance(response, dict):
        raw_status = response.get("status_code")
        if isinstance(raw_status, int):
            status_code = raw_status
        headers = response.get("headers")
        if isinstance(headers, dict):
            content_type = headers.get("content-type")

    return {
        "url": url,
        "path": path,
        "method": method,
        "status_code": status_code,
        "content_type": content_type,
    }


class KatanaHandler:
    """Normalise and render Katana endpoint-discovery output."""

    tool_name = "katana"
    domain = "web"
    segment = "web"
    should_enrich = False
    should_visualize = False
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "description"}
    )
    # Empty set → all type_* columns remain False (informational metadata only).
    type_flags: dict[str, set[str]] = {"informational": set()}
    enrichment_fields = None
    normalized_fields: list[str] = [
        "description",
        "finding_type",
        "method",
        "severity",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        """Katana is URL-discovery only post-Phase-9: emits no findings rows.

        Discovered URLs land in the ``url_findings`` table via the
        ``UrlInventoryIngestHandler`` instead. The parser still produces
        ``parsed_data`` (used by the OAS3 conversion in ``parse_output``)
        and the OAS3 file (consumed by ZAP/XSStrike/DalFox via the
        URL inventory artifact rebuild).
        """
        del result, profile
        return []

    def render(self, row: dict) -> str:
        """Render a normalised endpoint row as ChromaDB document text."""
        method = row.get("method", "")
        url = row.get("url", "")
        status_code = row.get("status_code", "")
        if status_code:
            return f"[katana] {method} {url} ({status_code})"
        return f"[katana] {method} {url}"

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "katana",
                str(finding.get("method", "")),
                str(finding.get("url", "")),
            ]
        )

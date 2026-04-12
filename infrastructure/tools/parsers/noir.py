"""Parser and handler for OWASP Noir OAS3 endpoint-discovery output.

Noir is an endpoint-discovery tool, not a vulnerability scanner. Its findings
are stored as ``informational`` records so that downstream steps (ChromaDB RAG,
triage) can see the application's attack surface without mistaking endpoint
metadata for exploitable vulnerabilities.

Following ADR-009 (nmap informational type), ``type_flags`` uses an empty set
so all ``type_*`` boolean columns remain ``False``; the ``finding_type`` JSON
field is the canonical classification.

``should_enrich = False`` because LLM enrichment adds no value to raw endpoint
metadata.

NOTE: The ``file`` field (source file path) cannot be populated from Noir's
OAS3 output (v0.25.1) because the OAS3 format does not include source file
metadata. The ``file`` column in findings rows is left as NULL.

The ``source_file`` field captures the OAS3 report file path itself, not the
source file where each endpoint was discovered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from domain.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta

# HTTP methods recognised as OAS3 path-item operations.
_OAS3_METHODS: frozenset[str] = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
)

# Path segments that indicate vendor/dependency directories.
# Shared with NoirHandler.normalize and BaseNoirTool.count_findings so the
# vendor-exclusion logic is applied consistently.
VENDOR_INDICATORS: frozenset[str] = frozenset(
    {
        "/vendor/",
        "/node_modules/",
        "/venv/",
        "/.venv/",
        "/site-packages/",
        "/__pycache__/",
        "/.git/",
        "/build/",
        "/dist/",
    }
)


def is_vendor_or_dependency_path(path: str) -> bool:
    """Return True if *path* looks like a vendor/dependency directory path."""
    path_lower = path.lower()
    return any(indicator in path_lower for indicator in VENDOR_INDICATORS)


# ---------------------------------------------------------------------------
# Parse functions (called by BaseNoirTool.parse_output)
# ---------------------------------------------------------------------------


def parse_noir_json(json_path: Path) -> dict[str, Any]:
    """Parse a Noir OAS3 output file into structured endpoint data."""
    try:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "error": f"OAS3 parse error: {exc}",
            "endpoints": [],
            "summary": {"total_endpoints": 0, "total_paths": 0},
        }
    return _parse_oas3_data(data)


def parse_noir_json_string(json_string: str) -> dict[str, Any]:
    """Parse Noir OAS3 JSON from a raw string into structured endpoint data."""
    stripped = json_string.strip() if json_string else ""
    if not stripped:
        return _parse_oas3_data({})
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return {
            "error": f"OAS3 parse error: {exc}",
            "raw_output": json_string[:500],
            "endpoints": [],
            "summary": {"total_endpoints": 0, "total_paths": 0},
        }
    return _parse_oas3_data(data)


# ---------------------------------------------------------------------------
# Internal parse helpers
# ---------------------------------------------------------------------------


def _parse_oas3_data(data: Any) -> dict[str, Any]:
    """Validate and deserialise an OAS3 document into endpoint records."""
    if not isinstance(data, dict):
        return {
            "error": "Unexpected OAS3 format (expected object at root)",
            "endpoints": [],
            "summary": {"total_endpoints": 0, "total_paths": 0},
        }

    # Soft version check — Noir always emits "3.0.x".
    openapi_version: str = data.get("openapi") or ""
    if openapi_version and not openapi_version.startswith("3."):
        return {
            "error": f"Expected OAS3 document, got openapi={openapi_version!r}",
            "endpoints": [],
            "summary": {"total_endpoints": 0, "total_paths": 0},
        }

    paths = data.get("paths")
    if not isinstance(paths, dict):
        return {
            "endpoints": [],
            "summary": {"total_endpoints": 0, "total_paths": 0},
        }

    endpoints: list[dict[str, Any]] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _OAS3_METHODS:
                continue
            endpoints.append(
                _parse_endpoint(str(path), method.upper(), operation or {})
            )

    return {
        "endpoints": endpoints,
        "summary": {
            "total_endpoints": len(endpoints),
            "total_paths": len(paths),
        },
    }


def _parse_endpoint(
    path: str, method: str, operation: dict[str, Any]
) -> dict[str, Any]:
    """Extract one endpoint record from a single OAS3 path+method operation."""
    raw_params: list[Any] = operation.get("parameters") or []
    parameters = [p for p in raw_params if isinstance(p, dict)]

    path_params = [_parse_param(p) for p in parameters if p.get("in") == "path"]
    query_params = [_parse_param(p) for p in parameters if p.get("in") == "query"]
    header_params = [_parse_param(p) for p in parameters if p.get("in") == "header"]
    cookie_params = [_parse_param(p) for p in parameters if p.get("in") == "cookie"]

    raw_body = operation.get("requestBody")
    body_params: list[dict[str, Any]] = (
        _parse_request_body(raw_body) if isinstance(raw_body, dict) else []
    )

    return {
        "path": path,
        "method": method,
        "path_params": path_params,
        "query_params": query_params,
        "header_params": header_params,
        "cookie_params": cookie_params,
        "body_params": body_params,
        "has_params": bool(
            path_params or query_params or header_params or cookie_params or body_params
        ),
    }


def _parse_param(param: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single OAS3 parameter object."""
    schema: dict[str, Any] = param.get("schema") or {}
    return {
        "name": str(param.get("name") or ""),
        "in": str(param.get("in") or ""),
        "required": bool(param.get("required", False)),
        "type": str(schema.get("type") or "string"),
    }


def _parse_request_body(request_body: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract parameter-like records from an OAS3 requestBody object."""
    content: dict[str, Any] = request_body.get("content") or {}
    params: list[dict[str, Any]] = []

    for content_type, media_type in content.items():
        mt: dict[str, Any] = media_type or {}
        schema: dict[str, Any] = mt.get("schema") or {}
        properties: dict[str, Any] = schema.get("properties") or {}
        required_props: list[str] = schema.get("required") or []

        if properties:
            for prop_name, prop_schema in properties.items():
                ps: dict[str, Any] = prop_schema or {}
                params.append(
                    {
                        "name": str(prop_name),
                        "in": "body",
                        "required": str(prop_name) in required_props,
                        "type": str(ps.get("type") or "string"),
                        "content_type": str(content_type),
                    }
                )
        else:
            # Schema has no named properties — emit a single body placeholder.
            params.append(
                {
                    "name": "_body",
                    "in": "body",
                    "required": bool(request_body.get("required", False)),
                    "type": str(schema.get("type") or "object"),
                    "content_type": str(content_type),
                }
            )

    return params


# ---------------------------------------------------------------------------
# Handler (normalize → SQLite rows, render → ChromaDB text)
# ---------------------------------------------------------------------------


def _uri_only(raw: str) -> str:
    """Strip scheme, host, and port from *raw*, returning only path+query+fragment.

    OAS3 paths are already URI-relative, but this guard ensures that if the
    parser ever surfaces a full URL (e.g. from Noir's native JSON mode), the
    ``url`` column never stores a host.

    Examples::

        "/api/users"                  → "/api/users"
        "http://host:9090/api/users"  → "/api/users"
        ""                            → ""
    """
    if not raw:
        return raw
    if "://" in raw:
        parsed = urlparse(raw)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        if parsed.fragment:
            path = f"{path}#{parsed.fragment}"
        return path
    return raw


class NoirHandler:
    """Normalise and render Noir endpoint-discovery output."""

    tool_name = "noir"
    domain = "code"
    segment = "web"
    should_enrich = False
    should_visualize = False
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "description"}
    )
    # Empty set → all type_* columns are False (see ADR-009 rationale).
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
        """Convert Noir ToolResult into one SQLite row per endpoint+method."""
        parsed: dict[str, Any] = result.parsed_data or {}
        endpoints: list[dict[str, Any]] = parsed.get("endpoints", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        rows: list[dict] = []

        for endpoint in endpoints:
            path: str = endpoint.get("path") or ""
            method: str = (endpoint.get("method") or "").upper()

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
                "url": _uri_only(path),
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

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "noir",
                str(finding.get("method", "")),
                str(finding.get("url", "")),
            ]
        )

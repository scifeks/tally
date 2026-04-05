"""Parser for OWASP Noir OAS3 output.

Noir writes an OpenAPI 3.x JSON document to the path given via ``-o``.  This
module deserialises that document into the canonical internal endpoint dict
used by ``NoirHandler.normalize()``.

No internal project imports — pure data transformation only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
# Public API
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
# Internal helpers
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

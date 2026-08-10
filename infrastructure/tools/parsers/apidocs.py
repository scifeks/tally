"""Parser for apidocs pipeline OAS3 output.

Reads the OAS3 YAML produced by the assemble stage, converts to JSON
for ingest handler compatibility, and extracts endpoint metadata.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def parse_apidocs_output(
    repo_path: str,
    output_file: str,
    files: dict[str, Path],
) -> dict[str, Any]:
    """Read the assembled OAS3 spec and produce structured data.

    Looks for YAML or JSON files in <repo>/apidocs/openapi/,
    merges them into a single OAS3 document, converts to JSON,
    and writes to output_file for the ingest handler.
    """
    openapi_dir = Path(repo_path) / "apidocs" / "openapi"
    if not openapi_dir.exists():
        return _error("apidocs/openapi/ directory not found")

    specs = list(openapi_dir.glob("*.yaml")) + list(openapi_dir.glob("*.json"))
    if not specs:
        return _error("no OAS3 files in apidocs/openapi/")

    merged_paths: dict[str, Any] = {}
    merged_doc: dict[str, Any] = {}

    for spec_path in specs:
        try:
            raw = spec_path.read_text(encoding="utf-8")
            if spec_path.suffix == ".yaml":
                doc = yaml.safe_load(raw)
            else:
                doc = json.loads(raw)
        except (
            OSError,
            yaml.YAMLError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning("Failed to parse %s: %s", spec_path, exc)
            continue

        if not isinstance(doc, dict):
            continue

        if not merged_doc:
            merged_doc = doc

        for path_key, ops in (doc.get("paths") or {}).items():
            if path_key not in merged_paths:
                merged_paths[path_key] = ops
            elif isinstance(ops, dict) and isinstance(merged_paths[path_key], dict):
                merged_paths[path_key].update(ops)

    if not merged_paths:
        return _error("no paths found in OAS3 specs")

    merged_doc["paths"] = merged_paths

    try:
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(merged_doc, indent=2), encoding="utf-8")
        files["oas3"] = out
    except OSError as exc:
        logger.warning("Failed to write OAS3 JSON: %s", exc)
        return _error(f"write failed: {exc}")

    endpoints = _extract_endpoints(merged_doc)
    return {
        "endpoints": endpoints,
        "summary": {
            "total_endpoints": len(endpoints),
            "source_files": [str(s) for s in specs],
        },
    }


def _extract_endpoints(doc: dict) -> list[dict[str, Any]]:
    """Extract flat endpoint records from an OAS3 document."""
    endpoints: list[dict[str, Any]] = []
    allowed = frozenset({"get", "post", "put", "delete", "patch", "head", "options"})
    for path, ops in (doc.get("paths") or {}).items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method.lower() not in allowed:
                continue
            endpoints.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "params": _count_params(op),
                }
            )
    return endpoints


def _count_params(op: Any) -> int:
    if not isinstance(op, dict):
        return 0
    count = len(op.get("parameters", []))
    body = op.get("requestBody")
    if isinstance(body, dict):
        count += 1
    return count


def _error(msg: str) -> dict[str, Any]:
    return {"error": msg, "endpoints": [], "summary": {}}

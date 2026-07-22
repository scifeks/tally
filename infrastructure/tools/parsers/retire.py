"""Parser and handler for Retire.js JSON output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from ._sca_shared import (
    _SCA_COMMON_ENRICHMENT_FIELDS,
    _build_sca_normalize,
    _sca_fingerprint_key,
    _sca_render,
)

logger = logging.getLogger(__name__)


def parse_retire_json(json_path: Path) -> dict[str, Any]:
    """Parse a Retire.js JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_retire_data(data)


def parse_retire_json_string(json_string: str) -> dict[str, Any]:
    """Parse Retire.js JSON from a raw string into structured data."""
    if not json_string or not json_string.strip():
        return {"error": "Empty JSON string"}
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_retire_data(data)


def _parse_retire_data(data: Any) -> dict[str, Any]:
    """Parse raw Retire.js array data into vulnerabilities and summary."""
    vulnerabilities: list[dict[str, Any]] = []

    if not isinstance(data, list):
        return {"error": "Expected a JSON array at top level"}

    for file_entry in data:
        file_path = file_entry.get("file", "")
        results = file_entry.get("results", [])

        for component_result in results:
            component = component_result.get("component", "")
            version = component_result.get("version", "")

            for vuln in component_result.get("vulnerabilities", []):
                parsed_vuln = _parse_vulnerability(vuln, component, version, file_path)
                vulnerabilities.append(parsed_vuln)

    by_severity: dict[str, int] = {}
    for v in vulnerabilities:
        sev = v["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "vulnerabilities": vulnerabilities,
        "summary": {
            "total_vulnerabilities": len(vulnerabilities),
            "by_severity": by_severity,
        },
    }


def _parse_vulnerability(
    vuln: dict[str, Any],
    component: str,
    version: str,
    file_path: str,
) -> dict[str, Any]:
    """Parse a single Retire.js vulnerability entry into normalized form."""
    identifiers = vuln.get("identifiers", {})
    cve_list: list[str] = identifiers.get("CVE", [])

    vulnerability_id = cve_list[0] if cve_list else ""
    aliases = cve_list[1:] if len(cve_list) > 1 else []

    return {
        "vulnerability_id": vulnerability_id,
        "aliases": aliases,
        "package_name": component,
        "package_version": version,
        "affected_ecosystem": "npm",
        "severity": vuln.get("severity", "low"),
        "summary": identifiers.get("summary", ""),
        "source_file": file_path,
        "references": vuln.get("info", []),
    }


class RetireHandler:
    tool_name = "retire"
    domain = "code"
    segment = "sca"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = _SCA_COMMON_ENRICHMENT_FIELDS
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }
    normalized_fields: list[str] = [
        "ecosystem",
        "file_path",
        "finding_type",
        "package_name",
        "package_version",
        "severity",
        "vulnerability_id",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        return _build_sca_normalize(self, result, profile)

    def render(self, row: dict) -> str:
        return _sca_render(row)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("retire", finding)

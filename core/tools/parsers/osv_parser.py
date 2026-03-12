"""Parser for OSV-Scanner JSON output."""

import json
from pathlib import Path
from typing import Any

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}


def parse_osv_json(json_path: Path) -> dict[str, Any]:
    """Parse an OSV-Scanner JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_osv_data(data)


def parse_osv_json_string(json_string: str) -> dict[str, Any]:
    """Parse OSV-Scanner JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_osv_data(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_osv_data(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    vulnerabilities: list[dict[str, Any]] = []
    packages_scanned = 0
    ecosystems: set = set()

    for result in results:
        source = result.get("source", {})
        source_path = source.get("path", "")
        source_type = source.get("type", "")
        for pkg in result.get("packages", []):
            packages_scanned += 1
            package = pkg.get("package", {})
            pkg_name = package.get("name", "")
            pkg_version = package.get("version", "")
            ecosystem = package.get("ecosystem", "")
            if ecosystem:
                ecosystems.add(ecosystem)

            for vuln in pkg.get("vulnerabilities", []):
                parsed_vuln = _parse_vulnerability(
                    vuln,
                    pkg_name,
                    pkg_version,
                    ecosystem,
                    source_path,
                    source_type,
                )
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
            "packages_scanned": packages_scanned,
            "ecosystems": sorted(ecosystems),
        },
    }


def _parse_vulnerability(
    vuln: dict[str, Any],
    pkg_name: str,
    pkg_version: str,
    ecosystem: str,
    source_file: str,
    source_type: str = "",
) -> dict[str, Any]:
    return {
        "vulnerability_id": vuln.get("id", ""),
        "aliases": vuln.get("aliases", []),
        "package_name": pkg_name,
        "package_version": pkg_version,
        "affected_ecosystem": ecosystem,
        "severity": _normalize_severity(vuln),
        "summary": vuln.get("summary", ""),
        "fixed_version": _extract_fixed_version(vuln, ecosystem, pkg_name),
        "cvss_score": _extract_cvss_score(vuln),
        "source_file": source_file,
        "source_type": source_type,
    }


def _normalize_severity(vuln: dict[str, Any]) -> str:
    """Derive a normalised severity label from CVSS score or database_specific."""
    cvss = _extract_cvss_score(vuln)
    if cvss is not None:
        if cvss >= 9.0:
            return "critical"
        if cvss >= 7.0:
            return "high"
        if cvss >= 4.0:
            return "medium"
        return "low"

    db_sev = vuln.get("database_specific", {}).get("severity", "").upper()
    return _SEVERITY_MAP.get(db_sev, "low")


def _extract_cvss_score(vuln: dict[str, Any]) -> float | None:
    """Return the numeric CVSS base score, or None if unavailable/unparseable."""
    for entry in vuln.get("severity", []):
        if entry.get("type", "").startswith("CVSS_V"):
            try:
                return float(entry.get("score", ""))
            except (ValueError, TypeError):
                continue
    return None


def _extract_fixed_version(
    vuln: dict[str, Any], ecosystem: str, pkg_name: str
) -> str | None:
    """Return the first fixed version from the affected ranges, or None."""
    for affected in vuln.get("affected", []):
        pkg = affected.get("package", {})
        if pkg.get("ecosystem") == ecosystem and pkg.get("name") == pkg_name:
            for rng in affected.get("ranges", []):
                if rng.get("type") == "ECOSYSTEM":
                    for event in rng.get("events", []):
                        if "fixed" in event:
                            return event["fixed"]
    return None

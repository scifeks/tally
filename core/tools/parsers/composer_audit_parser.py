"""Parser for composer audit JSON output."""
import json
from pathlib import Path
from typing import Any, Dict, List

# composer audit does not expose severity; all findings default to "low"
_DEFAULT_SEVERITY = "low"


def parse_composer_audit_json(json_path: Path) -> Dict[str, Any]:
    """Parse a composer audit JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_composer_audit_data(data)


def parse_composer_audit_json_string(json_string: str) -> Dict[str, Any]:
    """Parse composer audit JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_composer_audit_data(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_composer_audit_data(data: Dict[str, Any]) -> Dict[str, Any]:
    vulnerabilities: List[Dict[str, Any]] = []

    for pkg_name, advisories in data.get("advisories", {}).items():
        for advisory in advisories:
            cve = advisory.get("cve", "")
            advisory_id = advisory.get("advisoryId", "")
            vuln_id = cve or advisory_id

            vulnerabilities.append({
                "vulnerability_id": vuln_id,
                "package_name": pkg_name,
                "package_version": advisory.get("affectedVersions", ""),
                "affected_ecosystem": "Packagist",
                "severity": _DEFAULT_SEVERITY,
                "summary": advisory.get("title", ""),
                "fixed_version": None,
                "cvss_score": None,
                "source_file": advisory.get("link", ""),
            })

    by_severity: Dict[str, int] = {}
    for v in vulnerabilities:
        sev = v["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "vulnerabilities": vulnerabilities,
        "summary": {
            "total_vulnerabilities": len(vulnerabilities),
            "by_severity": by_severity,
            "packages_scanned": 0,
            "ecosystems": ["Packagist"],
        },
    }

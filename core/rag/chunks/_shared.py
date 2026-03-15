"""Shared helpers used by all chunk builders."""

from pathlib import Path
from typing import Any

from core.tools.constants import TOOL_DOMAIN_MAP, TOOL_TYPE_MAP


def _first_output_file(output_files: dict[str, Path]) -> str:
    """Return the string path of the first output file, or empty string."""
    if not output_files:
        return ""
    return str(next(iter(output_files.values())))


def _shared_meta(tool_name: str, finding_type: str) -> dict[str, Any]:
    """Return shared metadata fields for a given tool/finding_type combination."""
    _sca_flags = {"type_dependency", "type_vulnerability"}
    _TYPE_FLAGS: dict[tuple[str, str], set[str]] = {
        ("gitleaks", "secret"): {"type_secret"},
        ("semgrep", "vulnerability"): {"type_vulnerability", "type_weakness"},
        ("zap", "vulnerability"): {"type_vulnerability"},
        ("nmap", "informational"): set(),
        ("pip-audit", "dependency"): _sca_flags,
        ("npm-audit", "dependency"): _sca_flags,
        ("osv-scanner", "dependency"): _sca_flags,
        ("composer-audit", "dependency"): _sca_flags,
    }
    true_flags = _TYPE_FLAGS.get((tool_name, finding_type), set())
    booleans = {
        f"type_{t}": (f"type_{t}" in true_flags)
        for t in (
            "secret",
            "vulnerability",
            "weakness",
            "misconfiguration",
            "exposure",
            "dependency",
            "informational",
        )
    }
    return {
        "domain": TOOL_DOMAIN_MAP[tool_name],
        "tool_type": TOOL_TYPE_MAP[tool_name],
        "enriched": False,
        **booleans,
    }

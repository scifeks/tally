"""Shared helpers used by all chunk builders."""

from pathlib import Path
from typing import Any


def _first_output_file(output_files: dict[str, Path]) -> str:
    """Return the string path of the first output file, or empty string."""
    if not output_files:
        return ""
    return str(next(iter(output_files.values())))


def _shared_meta(builder: Any, finding_type: str) -> dict[str, Any]:
    """Return shared metadata fields for a given builder/finding_type combination."""
    true_flags = builder.type_flags.get(finding_type, set())
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
        "domain": builder.domain,
        "enriched": False,
        **booleans,
    }

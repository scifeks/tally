"""Probe Docker containers for installed SCA tool binaries."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

SCA_TOOLS_BY_LANGUAGE: dict[str, list[tuple[str, str]]] = {
    "python": [("pip-audit", "pip-audit")],
    "php": [("composer-audit", "composer")],
    "javascript": [("npm-audit", "npm")],
    "typescript": [("npm-audit", "npm")],
    "node": [("npm-audit", "npm")],
}


def probe_container_tools(
    container_name: str,
    languages: list[str],
) -> dict[str, str]:
    """Probe a container for SCA tool binaries.

    Returns a mapping of tool_name to the binary path inside the
    container for each detected tool. Languages without a known
    SCA tool mapping are silently skipped.
    """
    found: dict[str, str] = {}
    seen: set[str] = set()
    for lang in languages:
        entries = SCA_TOOLS_BY_LANGUAGE.get(lang.lower(), [])
        for tool_name, binary in entries:
            if tool_name in seen:
                continue
            seen.add(tool_name)
            path = _which_in_container(container_name, binary)
            if path:
                found[tool_name] = path
    return found


def _which_in_container(container_name: str, binary: str) -> str | None:
    """Run which inside a container and return the path."""
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "which", binary],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        logger.debug(
            "container_tool_probe: failed to probe %r in %r",
            binary,
            container_name,
            exc_info=True,
        )
    return None

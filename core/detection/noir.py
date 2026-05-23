"""Decide whether Noir should run for a repository."""

from __future__ import annotations

import re
from pathlib import Path

from core.config.schemas.repo_service import RepoService

# Python framework packages that Noir v0.25.1 does not support.
# When any of these appear in the repo's dependencies file Noir is skipped
# because it will fall back to scanning all files and emit garbage endpoints.
_NOIR_UNSUPPORTED_PACKAGES: frozenset[str] = frozenset(
    {
        "aiohttp",
        "bottle",
        "cherrypy",
        "falcon",
        "pyramid",
    }
)


def _is_node_app(repo_path: str) -> bool:
    """Return True when *repo_path* contains a package.json at its root."""
    if not repo_path:
        return False
    try:
        return (Path(repo_path) / "package.json").is_file()
    except OSError:
        return False


def _first_unsupported_package(deps_file: str) -> str:
    """Return the first unsupported package name found in *deps_file*, or ''."""
    if not deps_file:
        return ""
    try:
        text = Path(deps_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Extract the bare package name (strip version specifiers, extras,
        # env markers, and leading VCS prefixes such as "git+https://...").
        pkg = re.split(r"[\[=><! ;@~]", line)[0].lower().strip()
        if pkg in _NOIR_UNSUPPORTED_PACKAGES:
            return pkg
    return ""


def noir_skip_reason(service: RepoService, repo_path: str = "") -> str | None:
    """Return ``None`` if Noir should run, or a human-readable skip reason."""
    if service.docker_path:
        check_path = service.docker_path
    elif service.relative_path and repo_path:
        check_path = str(Path(repo_path) / service.relative_path)
    else:
        check_path = repo_path
    if _is_node_app(check_path):
        return "Node.js app"
    bad_pkg = _first_unsupported_package(service.dependencies_file)
    if bad_pkg:
        return f"unsupported framework ({bad_pkg})"
    return None

"""Dependency directory detection for scan tool exclusions.

Scans a repository directory for package manager files and returns the
corresponding dependency directories that should be excluded from analysis.

Used by Noir (and any future tool that scans source trees) to avoid
reporting routes or findings from vendored dependencies.
"""

from __future__ import annotations

from pathlib import Path

# Maps package manager file names to the dependency directory names they imply.
# Only directories that actually exist on disk are included in the result.
_LOCKFILE_TO_DEP_DIRS: dict[str, list[str]] = {
    "composer.json": ["vendor"],
    "composer.lock": ["vendor"],
    "package.json": ["node_modules"],
    "package-lock.json": ["node_modules"],
    "yarn.lock": ["node_modules"],
    "pnpm-lock.yaml": ["node_modules"],
    "requirements.txt": ["venv", ".venv"],
    "Pipfile": ["venv", ".venv"],
    "pyproject.toml": ["venv", ".venv"],
    "Gemfile": ["vendor/bundle"],
    "Gemfile.lock": ["vendor/bundle"],
    "go.mod": ["vendor"],
    "go.sum": ["vendor"],
}

# Directories excluded regardless of package manager files.
_ALWAYS_EXCLUDE: list[str] = [".git"]


def detect_dependency_dirs(repo_path: Path) -> list[str]:
    """Return dependency directory names to exclude for the given repo.

    Checks for package manager files and only includes directories that
    actually exist on disk.  Deduplicates while preserving insertion order.
    Always includes ``.git`` when present.

    Args:
        repo_path: Filesystem path to the repository root.

    Returns:
        Deduplicated list of directory names (e.g. ``["vendor", ".git"]``).
    """
    seen: set[str] = set()
    result: list[str] = []

    for lockfile, dep_dirs in _LOCKFILE_TO_DEP_DIRS.items():
        if not (repo_path / lockfile).exists():
            continue
        for dep_dir in dep_dirs:
            if dep_dir in seen:
                continue
            if (repo_path / dep_dir).exists():
                seen.add(dep_dir)
                result.append(dep_dir)

    for always in _ALWAYS_EXCLUDE:
        if always not in seen and (repo_path / always).exists():
            seen.add(always)
            result.append(always)

    return result


def build_exclude_path_prefixes(dep_dirs: list[str]) -> list[str]:
    """Convert dependency directory names to URL path prefix strings.

    Each name is wrapped with leading and trailing slashes so the prefix
    matches only proper directory segments in OAS3 endpoint paths and avoids
    false positives (e.g. ``/vendor/`` does not match ``/vendor-api/``).

    Args:
        dep_dirs: Directory names as returned by :func:`detect_dependency_dirs`.

    Returns:
        List of path prefix strings (e.g. ``["/vendor/", "/node_modules/"]``).
    """
    return [f"/{d.strip('/')}/" for d in dep_dirs]

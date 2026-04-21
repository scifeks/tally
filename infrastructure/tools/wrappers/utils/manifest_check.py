"""Utilities for detecting dependency manifests in a repository."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

LANGUAGE_MANIFESTS: dict[str, list[str]] = {
    "javascript": [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    ],
    "typescript": [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    ],
    "node": [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    ],
    "python": [
        "requirements.txt",
        "requirements.in",
        "requirements-dev.txt",
        "pyproject.toml",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "setup.py",
        "setup.cfg",
        "uv.lock",
        "pdm.lock",
        "constraints.txt",
    ],
    "php": ["composer.json", "composer.lock"],
}


def has_dependency_manifests(
    repo_path: str,
    languages: list[str],
) -> bool:
    """Return True if any language-appropriate manifest exists locally.

    Args:
        repo_path: Absolute path to the repository root.
        languages: List of language names (case-insensitive).
    """
    root = Path(repo_path)
    for lang in languages:
        manifests = LANGUAGE_MANIFESTS.get(lang.lower(), [])
        for manifest in manifests:
            if (root / manifest).exists():
                logger.debug(
                    "manifest_check: found %r for language %r in %r",
                    manifest,
                    lang,
                    repo_path,
                )
                return True
    return False


def has_dependency_manifests_docker(
    container_name: str,
    repo_path: str,
    languages: list[str],
) -> bool:
    """Return True if any language-appropriate manifest exists in a container.

    Uses ``docker exec <container> test -f <path>`` for each candidate.

    Args:
        container_name: Running Docker container name or ID.
        repo_path: Absolute path inside the container.
        languages: List of language names (case-insensitive).
    """
    for lang in languages:
        manifests = LANGUAGE_MANIFESTS.get(lang.lower(), [])
        for manifest in manifests:
            full_path = f"{repo_path.rstrip('/')}/{manifest}"
            try:
                result = subprocess.run(
                    ["docker", "exec", container_name, "test", "-f", full_path],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    logger.debug(
                        "manifest_check: found %r for language %r in "
                        "container %r at %r",
                        manifest,
                        lang,
                        container_name,
                        full_path,
                    )
                    return True
            except Exception as exc:
                logger.debug(
                    "manifest_check: docker test failed for %r: %s",
                    full_path,
                    exc,
                )
    return False


def has_manifests_for_language(
    repo_path: str,
    language: str,
    container_name: str = "",
) -> bool:
    """Return True if any manifest for ``language`` exists in the repo.

    Uses a local stat when ``container_name`` is empty, or ``docker exec
    test -f`` when it is set.

    Args:
        repo_path: Absolute path to the repository root (local or
            in-container path for docker mode).
        language: Language name (case-insensitive).
        container_name: If non-empty, check inside this container.
    """
    if container_name:
        return has_dependency_manifests_docker(container_name, repo_path, [language])
    return has_dependency_manifests(repo_path, [language])

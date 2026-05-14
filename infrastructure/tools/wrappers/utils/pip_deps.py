"""Utilities for detecting and exporting Python dependency files."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Prevent repeated export attempts within a single session.
# Keys: repo_path
_attempted: set[str] = set()


def reset_attempted() -> None:
    """Clear the dedup set for use in tests only."""
    _attempted.clear()


def find_or_generate_requirements(
    repo_path: str,
    container_name: str = "",
    timeout: int = 120,
) -> str | None:
    """Find or generate a pip-audit-compatible requirements file."""
    root = Path(repo_path)

    def _exists(filename: str) -> bool:
        if container_name:
            full = f"{repo_path.rstrip('/')}/{filename}"
            try:
                r = subprocess.run(
                    ["docker", "exec", container_name, "test", "-f", full],
                    capture_output=True,
                    timeout=10,
                )
                return r.returncode == 0
            except Exception as exc:
                logger.debug("pip_deps: docker test failed for %r: %s", full, exc)
                return False
        return (root / filename).exists()

    def _run(cmd: list[str], out_file: str) -> str | None:
        """Execute command and write stdout to file."""
        logger.info("pip_deps: running %s", " ".join(cmd))
        try:
            if container_name:
                full_cmd = [
                    "docker",
                    "exec",
                    "-w",
                    repo_path,
                    container_name,
                    *cmd,
                ]
                result = subprocess.run(
                    full_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            else:
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
        except Exception as exc:
            logger.warning("pip_deps: export command raised: %s", exc)
            return None

        if result.stderr:
            logger.debug("pip_deps stderr: %s", result.stderr)

        if result.returncode != 0:
            logger.warning(
                "pip_deps: export command exited rc=%d; skipping",
                result.returncode,
            )
            return None

        if not result.stdout.strip():
            logger.warning("pip_deps: export command produced no output; skipping")
            return None

        dest = root / out_file
        dest.write_text(result.stdout)
        logger.info("pip_deps: wrote %r", str(dest))
        return str(dest)

    if _exists("requirements.txt"):
        logger.debug("pip_deps: using existing requirements.txt in %r", repo_path)
        return str(root / "requirements.txt")

    if repo_path in _attempted:
        logger.debug("pip_deps: export already attempted for %r; skipping", repo_path)
        return None

    _attempted.add(repo_path)

    if _exists("poetry.lock"):
        return _run(
            [
                "poetry",
                "export",
                "--without-hashes",
                "-f",
                "requirements.txt",
            ],
            ".tally_requirements.txt",
        )

    if _exists("Pipfile.lock"):
        return _run(["pipenv", "requirements"], ".tally_requirements.txt")

    for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
        if _exists(marker):
            return _run(
                ["pip", "freeze"],
                ".tally_requirements.txt",
            )

    logger.info("pip_deps: no Python dependency files found in %r", repo_path)
    return None

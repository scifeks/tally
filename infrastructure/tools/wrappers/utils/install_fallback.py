"""Shared utility for generating missing lockfiles before SCA scans."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_attempted: set[tuple[str, str]] = set()


def reset_attempted() -> None:
    """Clear the dedup set for use in tests only."""
    _attempted.clear()


def ensure_lockfile(
    tool_name: str,
    repo_path: str,
    lockfile_name: str,
    install_cmd: list[str],
    container_name: str = "",
    timeout: int = 120,
) -> bool:
    """Generate *lockfile_name* if absent; return whether it exists."""

    def _file_exists() -> bool:
        if container_name:
            full = f"{repo_path.rstrip('/')}/{lockfile_name}"
            try:
                r = subprocess.run(
                    ["docker", "exec", container_name, "test", "-f", full],
                    capture_output=True,
                    timeout=10,
                )
                return r.returncode == 0
            except Exception:
                return False
        return (Path(repo_path) / lockfile_name).exists()

    if _file_exists():
        return True

    key = (tool_name, repo_path)
    if key in _attempted:
        logger.debug(
            "%s: install already attempted for %r; skipping",
            tool_name,
            repo_path,
        )
        return False

    _attempted.add(key)
    logger.info(
        "%s: %r not found in %r; attempting: %s",
        tool_name,
        lockfile_name,
        repo_path,
        " ".join(install_cmd),
    )

    try:
        if container_name:
            cmd = [
                "docker",
                "exec",
                "-w",
                repo_path,
                container_name,
                *install_cmd,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            result = subprocess.run(
                install_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    except Exception as exc:
        logger.warning(
            "%s: install command raised an exception: %s; scan will be skipped",
            tool_name,
            exc,
        )
        return False

    if result.stdout:
        logger.debug("%s install stdout: %s", tool_name, result.stdout)
    if result.stderr:
        logger.debug("%s install stderr: %s", tool_name, result.stderr)

    if result.returncode != 0:
        logger.warning(
            "%s: install command exited with rc=%d; scan will be skipped",
            tool_name,
            result.returncode,
        )
        return False

    # Verify the file was actually created.
    if not _file_exists():
        logger.warning(
            "%s: install succeeded (rc=0) but %r still not found in %r; "
            "scan will be skipped",
            tool_name,
            lockfile_name,
            repo_path,
        )
        return False

    logger.info(
        "%s: %r generated successfully",
        tool_name,
        lockfile_name,
    )
    return True

"""pip-audit wrapper for Python dependency vulnerability scanning (SCA)."""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.pip_audit import BasePipAuditTool

logger = logging.getLogger(__name__)

# Prevent repeated install attempts within a single session.
_install_attempted: bool = False


class PipAuditLocalTool(BasePipAuditTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "pip-audit"

    def check_available(self) -> bool:
        global _install_attempted
        if shutil.which("pip-audit") is not None:
            return True
        if _install_attempted:
            return False
        _install_attempted = True
        logger.info("pip-audit not found; attempting auto-install via pip...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--user", "pip-audit"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                # Refresh PATH lookup after install (pip --user may add to PATH).
                import importlib
                import os

                user_bin = (
                    Path(
                        subprocess.check_output(
                            [sys.executable, "-m", "site", "--user-base"],
                            text=True,
                        ).strip()
                    )
                    / "bin"
                )
                os.environ["PATH"] = (
                    str(user_bin) + os.pathsep + os.environ.get("PATH", "")
                )
                importlib.invalidate_caches()
                if shutil.which("pip-audit") is not None:
                    logger.info("pip-audit installed successfully.")
                    return True
            logger.warning(
                "pip-audit auto-install failed (rc=%d). "
                "Install manually with: pip install pip-audit",
                result.returncode,
            )
        except Exception as exc:
            logger.warning("pip-audit auto-install error: %s", exc)
        return False

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        """Build the pip-audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            dependencies_file (str): Local path to the dependencies file.
                When set, passes ``-r <dependencies_file>`` to pip-audit to
                scope the scan to declared dependencies.  The base class
                ensures this is always non-empty for local runs (repos without
                a dependencies file are skipped before reaching here).
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for pip-audit")
        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")
        dependencies_file: str = kwargs.get("dependencies_file", "")
        cmd = ["pip-audit", "--format", "json"]
        if dependencies_file:
            cmd.extend(["-r", dependencies_file])
        return cmd

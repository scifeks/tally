"""OSV-Scanner wrapper for dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path

from domain.tools.base import get_tool_version
from infrastructure.tools.wrappers.base.osv_scanner import BaseOSVScannerTool


class OSVScannerLocalTool(BaseOSVScannerTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "osv-scanner"

    def check_available(self) -> bool:
        return shutil.which("osv-scanner") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        """Build the osv-scanner argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            recursive (bool): Recursively scan subdirectories (default: True).
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for osv-scanner")
        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        recursive: bool = kwargs.get("recursive", True)

        # --format json sends findings as JSON to stdout; executor captures it
        cmd = ["osv-scanner", "--format", "json", "--allow-no-lockfiles"]
        if recursive:
            cmd.append("--recursive")
        cmd.append(repo_path)
        return cmd

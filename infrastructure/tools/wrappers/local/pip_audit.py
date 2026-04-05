"""pip-audit wrapper for Python dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.pip_audit import BasePipAuditTool


class PipAuditLocalTool(BasePipAuditTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "pip-audit"

    def check_available(self) -> bool:
        return shutil.which("pip-audit") is not None

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

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

        Runs pip-audit with no requirements flag so it audits the ambient
        Python environment from the repository directory (cwd is set by
        build_execution_passes). Avoids triggering venv creation which fails
        for projects with Python 3.13-incompatible build dependencies.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for pip-audit")
        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")
        return ["pip-audit", "--format", "json"]

"""pip-audit wrapper for Python dependency vulnerability scanning (SCA)."""

import shutil
import sys
from pathlib import Path

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.pip_audit import BasePipAuditTool


def _find_pip_audit() -> str | None:
    """Locate pip-audit on PATH or in the running interpreter's bin directory."""
    found = shutil.which("pip-audit")
    if found:
        return found
    venv_candidate = Path(sys.executable).parent / "pip-audit"
    if venv_candidate.is_file():
        return str(venv_candidate)
    return None


class PipAuditLocalTool(BasePipAuditTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return _find_pip_audit() or "pip-audit"

    def check_available(self) -> bool:
        return _find_pip_audit() is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for pip-audit")
        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")
        dependencies_file: str = kwargs.get("dependencies_file", "")
        cmd = [self.command, "--format", "json"]
        if dependencies_file:
            cmd.extend(["-r", dependencies_file])
        return cmd

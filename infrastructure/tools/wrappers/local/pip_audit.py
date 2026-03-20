"""pip-audit wrapper for Python dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path

from domain.tools.base import get_tool_version
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

        The command targets requirements.txt if present, otherwise falls back
        to --path for projects using pyproject.toml / setup.cfg / setup.py.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for pip-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        cmd = ["pip-audit", "--format", "json"]

        req_file = repo / "requirements.txt"
        if req_file.exists():
            cmd.extend(["-r", str(req_file)])
        elif (
            (repo / "pyproject.toml").exists()
            or (repo / "setup.cfg").exists()
            or (repo / "setup.py").exists()
        ):
            cmd.extend(["--path", str(repo)])
        else:
            raise ValueError(
                "No Python manifest (requirements.txt, pyproject.toml, setup.py)"
                f" found in {repo_path!r}"
            )

        return cmd

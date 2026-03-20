"""npm-audit wrapper for Node.js dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path

from domain.tools.base import get_tool_version
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.wrappers.base.npm_audit import BaseNpmAuditTool


class NpmAuditLocalTool(BaseNpmAuditTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "npm"

    def check_available(self) -> bool:
        return shutil.which("npm") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        """Build the npm audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
                             Must contain a package.json file.

        Note:
            npm audit must run in the directory containing package.json.
            The executor must be called with ``cwd=repo_path`` so the
            subprocess runs inside the repository directory.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for npm-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        if not (repo / "package.json").exists():
            raise ValueError(f"No package.json found in {repo_path!r}")

        return ["npm", "audit", "--json"]

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
                cwd=repo_path,
            )
        ]

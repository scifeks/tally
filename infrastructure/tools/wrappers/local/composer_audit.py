"""composer-audit wrapper for PHP dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.composer_audit import BaseComposerAuditTool


class ComposerAuditLocalTool(BaseComposerAuditTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "composer"

    def check_available(self) -> bool:
        return shutil.which("composer") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        """Build the composer audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
                             Must contain a composer.json file.

        Note:
            composer audit must run in the directory containing composer.json.
            The executor must be called with ``cwd=repo_path`` so the
            subprocess runs inside the repository directory.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for composer-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        if not (repo / "composer.json").exists():
            raise ValueError(f"No composer.json found in {repo_path!r}")

        return ["composer", "audit", "--format=json"]

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

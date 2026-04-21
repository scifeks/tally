"""Docker wrapper for npm-audit Node.js dependency vulnerability scanning."""

import logging

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.wrappers.base.npm_audit import BaseNpmAuditTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec
from infrastructure.tools.wrappers.utils.install_fallback import ensure_lockfile

logger = logging.getLogger(__name__)


class NpmAuditDockerTool(BaseNpmAuditTool):
    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs) -> list[str]:
        """Build docker exec argv for npm audit.

        Runs ``npm audit --json`` inside the repository directory via
        ``-w <docker_path>``.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        tool_args = ["audit", "--json"]
        return build_docker_exec(
            self._container_name, self._tool_path, tool_args, workdir=repo_path
        )

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)

        if not ensure_lockfile(
            "npm-audit",
            repo_path,
            "package-lock.json",
            ["npm", "install", "--package-lock-only"],
            container_name=self._container_name,
        ):
            return []

        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
            )
        ]

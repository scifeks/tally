"""Docker wrapper for pip-audit Python dependency vulnerability scanning."""

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.wrappers.base.pip_audit import BasePipAuditTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class PipAuditDockerTool(BasePipAuditTool):
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

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={
                    "repo_path": repo_path,
                    "dependencies_file": context.repo.dependencies_file,
                },
            )
        ]

    def build_command(self, **kwargs) -> list[str]:
        """Build docker exec argv for pip-audit.

        When ``dependencies_file`` is set, scopes the scan to the declared
        dependencies via ``-r <dependencies_file>``.  When absent, runs
        pip-audit with no ``-r`` flag, scanning all packages installed in
        the container environment.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
            dependencies_file (str): Container path to the dependencies file,
                or empty string for a full environment scan.
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )
        dependencies_file: str = kwargs.get("dependencies_file", "")
        tool_args = ["--format", "json"]
        if dependencies_file:
            tool_args.extend(["-r", dependencies_file])
        return build_docker_exec(
            self._container_name, self._tool_path, tool_args, workdir=repo_path
        )

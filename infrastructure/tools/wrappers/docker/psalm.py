from infrastructure.tools.wrappers.base.psalm import BasePsalmTool
from infrastructure.tools.wrappers.docker._docker_exec import (
    build_docker_exec,
)


class PsalmDockerTool(BasePsalmTool):
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
        repo_path: str = kwargs.get("repo_path", "")
        config_path: str = kwargs.get("config_path", "")
        sarif_path: str = kwargs.get("sarif_path", "")

        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this "
                "repository. Use 'edit-repo' to set the "
                "container mount path."
            )

        tool_args = [
            f"--config={config_path}",
            f"--report={sarif_path}",
            "--no-cache",
            "--no-progress",
        ]

        return build_docker_exec(
            self._container_name,
            self._tool_path,
            tool_args,
        )

"""Docker wrapper for OSV-Scanner dependency vulnerability scanning."""

from infrastructure.tools.wrappers.base.osv_scanner import BaseOSVScannerTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class OSVScannerDockerTool(BaseOSVScannerTool):
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
        """Build docker exec argv for osv-scanner.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
            recursive (bool): Recursively scan subdirectories (default: True).
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        recursive: bool = kwargs.get("recursive", True)

        tool_args = ["--format", "json"]
        if recursive:
            tool_args.append("--recursive")
        tool_args.append(repo_path)

        return build_docker_exec(self._container_name, self._tool_path, tool_args)

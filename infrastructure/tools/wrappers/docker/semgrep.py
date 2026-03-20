"""Docker wrapper for semgrep static analysis."""

from infrastructure.tools.wrappers.base.semgrep import BaseSemgrepTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class SemgrepDockerTool(BaseSemgrepTool):
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
        """Build docker exec argv for semgrep.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
            config (str): Semgrep ruleset (default: "auto").
            severity (List[str]): Severity filter list.
            exclude (List[str]): Glob patterns to exclude.
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        ruleset: str = kwargs.get("config", "auto")
        severity: list[str] | None = kwargs.get("severity")
        exclude: list[str] | None = kwargs.get("exclude")

        tool_args = ["scan", "--config", ruleset, "--json", repo_path]

        if severity:
            for sev in severity:
                tool_args.extend(["--severity", sev.upper()])

        if exclude:
            for pattern in exclude:
                tool_args.extend(["--exclude", pattern])

        return build_docker_exec(self._container_name, self._tool_path, tool_args)

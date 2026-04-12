"""Docker wrapper for gitleaks secrets detection."""

from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.gitleaks import (
    parse_gitleaks_json,
    parse_gitleaks_json_string,
)
from infrastructure.tools.wrappers.base.gitleaks import BaseGitleaksTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class GitleaksDockerTool(BaseGitleaksTool):
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
        """Build docker exec argv for gitleaks.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
            scan_type (str): 'dir' for working-tree scan or 'git' for full
                             history scan (default: 'dir').
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        scan_type: str = kwargs.get("scan_type", "dir")
        if scan_type not in ("dir", "git"):
            raise ValueError(f"scan_type must be 'dir' or 'git', got {scan_type!r}")

        gitleaks_ignore_path: str | None = kwargs.get("gitleaks_ignore_path")

        tool_args = [
            scan_type,
            repo_path,
            "--report-format",
            "json",
            "--exit-code",
            "0",
        ]
        if gitleaks_ignore_path:
            tool_args.extend(["--gitleaks-ignore-path", gitleaks_ignore_path])

        return build_docker_exec(self._container_name, self._tool_path, tool_args)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_gitleaks_json(json_path)
        return parse_gitleaks_json_string(output)

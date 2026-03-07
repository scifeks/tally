"""Docker wrapper for pip-audit Python dependency vulnerability scanning."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import DockerToolWrapper
from ...parsers.pip_audit_parser import parse_pip_audit_json, parse_pip_audit_json_string


class DockerPipAuditWrapper(DockerToolWrapper):
    @property
    def name(self) -> str:
        return "pip-audit"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Python dependency vulnerability scanner using PyPI advisory database"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return ["python"]

    def build_command(self, **kwargs) -> List[str]:
        """Build docker exec argv for pip-audit.

        Runs ``pip-audit --format json --path .`` inside the repository
        directory via ``-w <docker_path>``.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        tool_args = ["--format", "json", "--path", "."]
        return self._build_docker_exec(tool_args, workdir=repo_path)

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_pip_audit_json(json_path)
        return parse_pip_audit_json_string(output)

"""Docker wrapper for composer-audit PHP dependency vulnerability scanning."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import DockerToolWrapper
from ...parsers.composer_audit_parser import (
    parse_composer_audit_json,
    parse_composer_audit_json_string,
)


class DockerComposerAuditWrapper(DockerToolWrapper):
    @property
    def name(self) -> str:
        return "composer-audit"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "PHP dependency vulnerability scanner using Packagist security advisories"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return ["php"]

    def build_command(self, **kwargs) -> List[str]:
        """Build docker exec argv for composer audit.

        Runs ``composer audit --format=json`` inside the repository directory
        via ``-w <docker_path>``.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        tool_args = ["audit", "--format=json"]
        return self._build_docker_exec(tool_args, workdir=repo_path)

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_composer_audit_json(json_path)
        return parse_composer_audit_json_string(output)

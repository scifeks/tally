"""Docker wrapper for semgrep static analysis."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import DockerToolWrapper
from ...parsers.semgrep_parser import parse_semgrep_json, parse_semgrep_json_string


class DockerSemgrepWrapper(DockerToolWrapper):
    @property
    def name(self) -> str:
        return "semgrep"

    @property
    def category(self) -> str:
        return "sast"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Static analysis tool for finding bugs and security issues"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return None

    def build_command(self, **kwargs) -> List[str]:
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
        severity: Optional[List[str]] = kwargs.get("severity")
        exclude: Optional[List[str]] = kwargs.get("exclude")

        tool_args = ["scan", "--config", ruleset, "--json", repo_path]

        if severity:
            for sev in severity:
                tool_args.extend(["--severity", sev.upper()])

        if exclude:
            for pattern in exclude:
                tool_args.extend(["--exclude", pattern])

        return self._build_docker_exec(tool_args)

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_semgrep_json(json_path)
        return parse_semgrep_json_string(output)

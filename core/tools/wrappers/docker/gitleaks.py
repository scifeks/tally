"""Docker wrapper for gitleaks secrets detection."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import DockerToolWrapper
from ...parsers.gitleaks_parser import parse_gitleaks_json, parse_gitleaks_json_string


class DockerGitleaksWrapper(DockerToolWrapper):
    @property
    def name(self) -> str:
        return "gitleaks"

    @property
    def category(self) -> str:
        return "secrets"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Secrets detection tool for git repositories and files"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return None

    def build_command(self, **kwargs) -> List[str]:
        """Build docker exec argv for gitleaks.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
            scan_uncommitted (bool): Scan uncommitted changes (default: False).
            verbose (bool): Enable verbose output (default: False).
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )

        scan_uncommitted: bool = bool(kwargs.get("scan_uncommitted", False))
        verbose: bool = bool(kwargs.get("verbose", False))

        tool_args = [
            "detect",
            "--source", repo_path,
            "--report-format", "json",
        ]

        if scan_uncommitted:
            tool_args.append("--uncommitted")
        else:
            tool_args.append("--no-git")

        if verbose:
            tool_args.append("--verbose")

        return self._build_docker_exec(tool_args)

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_gitleaks_json(json_path)
        return parse_gitleaks_json_string(output)

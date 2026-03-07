"""Docker wrapper for OSV-Scanner dependency vulnerability scanning."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import DockerToolWrapper
from ...parsers.osv_parser import parse_osv_json, parse_osv_json_string


class DockerOSVScannerWrapper(DockerToolWrapper):
    @property
    def name(self) -> str:
        return "osv-scanner"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Dependency vulnerability scanner using OSV database"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return None

    def build_command(self, **kwargs) -> List[str]:
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

        return self._build_docker_exec(tool_args)

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_osv_json(json_path)
        return parse_osv_json_string(output)

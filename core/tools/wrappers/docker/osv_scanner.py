"""Docker wrapper for OSV-Scanner dependency vulnerability scanning."""

from pathlib import Path
from typing import Any

from ...base import DockerToolWrapper, ToolResult
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.osv_parser import parse_osv_json, parse_osv_json_string


class DockerOSVScannerWrapper(ToolInterface, DockerToolWrapper):
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
    def scan_segment(self) -> str:
        return "sca"

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

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

        return self._build_docker_exec(tool_args)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_osv_json(json_path)
        return parse_osv_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        result = summary.get(
            "total_vulnerabilities", len(parsed_data.get("vulnerabilities", []))
        )
        # TODO: revisit when normalized schema is introduced
        return result

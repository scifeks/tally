import shutil
from pathlib import Path
from typing import Any

from ...base import ToolResult, ToolWrapper
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.semgrep_parser import parse_semgrep_json, parse_semgrep_json_string


class SemgrepWrapper(ToolInterface, ToolWrapper):
    def __init__(self, config=None) -> None:
        pass

    @property
    def name(self) -> str:
        return "semgrep"

    @property
    def command(self) -> str:
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
    def scan_segment(self) -> str:
        return "sast"

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

    def check_available(self) -> bool:
        return shutil.which("semgrep") is not None

    def build_command(self, **kwargs) -> list[str]:
        """Build the semgrep argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            config (str): Semgrep ruleset/config (default: "auto").
            severity (List[str]): Only report findings at these severities.
            exclude (List[str]): Glob patterns for paths to exclude.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for semgrep")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        config: str = kwargs.get("config", "auto")
        severity: list[str] | None = kwargs.get("severity")
        exclude: list[str] | None = kwargs.get("exclude")

        # --json sends findings as JSON to stdout; executor captures and saves it
        cmd = ["semgrep", "scan", "--config", config, "--json", repo_path]

        if severity:
            for sev in severity:
                cmd.extend(["--severity", sev.upper()])

        if exclude:
            for pattern in exclude:
                cmd.extend(["--exclude", pattern])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse semgrep JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_semgrep_json(json_path)
        return parse_semgrep_json_string(output)

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
        if "total_findings" in summary:
            return summary["total_findings"]
        # fallback must not be removed
        result = len(parsed_data.get("findings", []))
        # TODO: revisit when normalized schema is introduced
        return result

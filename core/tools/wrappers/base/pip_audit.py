"""Shared base class for pip-audit local and docker wrappers."""

from pathlib import Path
from typing import Any

from ...base import ToolResult
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.pip_audit_parser import (
    parse_pip_audit_json,
    parse_pip_audit_json_string,
)


class BasePipAuditTool(ToolInterface):
    _candidate_commands: list[str] = ["pip-audit"]
    _command_entry_type: str = "repo"

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
    def scan_segment(self) -> str:
        return "sca"

    @property
    def skip(self) -> bool:
        return False

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return ["python"]

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def always_run(self) -> bool:
        return False

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse pip-audit JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_pip_audit_json(json_path)
        return parse_pip_audit_json_string(output)

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

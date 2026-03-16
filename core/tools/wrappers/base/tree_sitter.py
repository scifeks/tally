"""Shared base class for tree-sitter local wrapper."""

from typing import Any

from ...base import ToolResult
from ...interface import ExecutionContext, ExecutionPass, ToolInterface


class BaseTreeSitterTool(ToolInterface):
    _candidate_commands: list[str] = []  # library tool, no binary to discover
    _command_entry_type: str = "repo"

    @property
    def name(self) -> str:
        return "tree-sitter"

    @property
    def category(self) -> str:
        return "sast"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "Structural code analysis via tree-sitter"
            " (functions, classes, imports, calls)"
        )

    @property
    def scan_segment(self) -> str:
        return "structure"

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
    def always_run(self) -> bool:
        return True

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return None

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
        if "total_files" in summary:
            return summary["total_files"]
        return len(parsed_data.get("files", []))

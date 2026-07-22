"""Shared base class for Retire.js local and docker wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface
from infrastructure.tools.parsers.retire import (
    parse_retire_json,
    parse_retire_json_string,
)


class BaseRetireTool(ToolInterface):
    """Base class for Retire.js vulnerable JavaScript library detector."""

    _candidate_commands: list[str] = ["retire"]
    _command_entry_type: str = "repo"

    @property
    def name(self) -> str:
        return "retire"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "Retire.js vulnerable JavaScript library detector; scans JS "
            "files directly for known CVEs without requiring a lockfile"
        )

    @property
    def scan_segment(self) -> str:
        return "sca"

    @property
    def skip(self) -> bool:
        return False

    @property
    def should_visualize(self) -> bool:
        return True

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return ["javascript"]

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
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_retire_json(json_path)
        return parse_retire_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        assert context.service is not None
        repo_path = context.registry.get_service_path(
            self.name, context.service, context.repo.path
        )
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
            "total_vulnerabilities",
            len(parsed_data.get("vulnerabilities", [])),
        )
        return result

"""Shared base class for pip-audit local and docker wrappers."""

import logging
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface
from infrastructure.tools.parsers.pip_audit import (
    parse_pip_audit_json,
    parse_pip_audit_json_string,
)
from infrastructure.tools.wrappers.utils.pip_deps import find_or_generate_requirements

logger = logging.getLogger(__name__)


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
    def should_visualize(self) -> bool:
        return True

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
        if context.is_docker:
            deps_file = context.repo.dependencies_file
        else:
            # Local mode: never pass container_name. The repo may have a
            # container configured for other tools, but pip-audit runs
            # locally and must check the local filesystem only.
            deps_file = find_or_generate_requirements(repo_path)
            if not deps_file:
                logger.info(
                    "pip-audit: no Python dependency file found in %r; skipping",
                    repo_path,
                )
                return []
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={
                    "repo_path": repo_path,
                    "dependencies_file": deps_file,
                },
                cwd=repo_path,
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

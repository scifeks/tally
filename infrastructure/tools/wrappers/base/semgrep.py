"""Shared base class for semgrep local and docker wrappers."""

import logging
from pathlib import Path
from typing import Any

from core.config.schemas import build_excluded_dirs
from domain.tools.base import ToolResult
from domain.tools.interface import (
    ExecutionContext,
    ExecutionPass,
    ToolInterface,
)
from infrastructure.tools.parsers.semgrep import (
    parse_semgrep_json,
    parse_semgrep_json_string,
)
from infrastructure.tools.parsers.semgrep_traces import (
    merge_traces,
    parse_traces,
)

_log = logging.getLogger(__name__)


class BaseSemgrepTool(ToolInterface):
    _candidate_commands: list[str] = ["semgrep"]
    _command_entry_type: str = "repo"
    supports_include: bool = True

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
    def scan_segment(self) -> str:
        return "sast"

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
        return self.language_gates or None

    def parse_output(
        self,
        output: str,
        files: dict[str, Path],
    ) -> dict[str, Any]:
        """Parse semgrep output into structured data.

        Prefers the saved stdout file; falls back to the
        output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_semgrep_json(json_path)
        return parse_semgrep_json_string(output)

    def build_execution_passes(
        self,
        context: ExecutionContext,
    ) -> list[ExecutionPass]:
        assert context.repo is not None
        assert context.service is not None
        repo_path = context.registry.get_service_path(
            self.name,
            context.service,
            context.repo.path,
        )
        exclude = build_excluded_dirs(context.service)
        kwargs: dict[str, object] = {"repo_path": repo_path}
        if exclude:
            kwargs["exclude"] = exclude
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs=kwargs,
            ),
            ExecutionPass(
                label_suffix=f"{context.repo.name}_traces",
                kwargs={**kwargs, "trace_mode": True},
            ),
        ]

    def merge_pass_results(
        self,
        pass_results: list[ToolResult],
    ) -> ToolResult:
        json_result = pass_results[0]
        if len(pass_results) < 2:
            return json_result

        trace_result = pass_results[1]
        parsed = json_result.parsed_data
        if parsed and trace_result.output:
            try:
                traces = parse_traces(trace_result.output)
                findings = parsed.get("findings", [])
                merge_traces(findings, traces)
            except Exception:
                _log.exception("Failed to parse trace output")

        combined_files = dict(json_result.output_files)
        for k, v in trace_result.output_files.items():
            combined_files[f"trace_{k}"] = v

        return ToolResult(
            tool_name="semgrep",
            success=json_result.success,
            output=json_result.output,
            parsed_data=parsed,
            output_files=combined_files,
            timestamp=json_result.timestamp,
            duration_seconds=(
                json_result.duration_seconds + trace_result.duration_seconds
            ),
        )

    def count_findings(
        self,
        parsed_data: dict[str, Any],
    ) -> int:
        summary = parsed_data.get("summary", {})
        if "total_findings" in summary:
            return summary["total_findings"]
        # fallback must not be removed
        result = len(parsed_data.get("findings", []))
        return result

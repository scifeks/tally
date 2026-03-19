"""Shared base class for gitleaks local and docker wrappers."""

from typing import Any

from ...base import ToolResult
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.gitleaks_parser import combine_gitleaks_results


class BaseGitleaksTool(ToolInterface):
    _candidate_commands: list[str] = ["gitleaks"]
    _command_entry_type: str = "repo"

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
    def scan_segment(self) -> str:
        return "secrets"

    @property
    def skip(self) -> bool:
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

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=f"{context.repo.name}_dir",
                kwargs={"repo_path": repo_path, "scan_type": "dir"},
            ),
            ExecutionPass(
                label_suffix=f"{context.repo.name}_git",
                kwargs={"repo_path": repo_path, "scan_type": "git"},
            ),
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        """Mirrors _run_gitleaks_both_scans in orchestrator.py."""
        dir_result, git_result = pass_results[0], pass_results[1]
        dir_data = dir_result.parsed_data or {}
        git_data = git_result.parsed_data or {}
        combined_data = combine_gitleaks_results(dir_data, git_data)
        combined_files = {f"dir_{k}": v for k, v in dir_result.output_files.items()}
        combined_files.update(
            {f"git_{k}": v for k, v in git_result.output_files.items()}
        )
        return ToolResult(
            tool_name="gitleaks",
            success=dir_result.success or git_result.success,
            output=(dir_result.output or "") + "\n" + (git_result.output or ""),
            parsed_data=combined_data,
            output_files=combined_files,
            timestamp=dir_result.timestamp,
            duration_seconds=(
                dir_result.duration_seconds + git_result.duration_seconds
            ),
        )

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        result = parsed_data.get("summary", {}).get(
            "total_secrets", len(parsed_data.get("secrets", []))
        )
        # TODO: revisit when normalized schema is introduced
        return result

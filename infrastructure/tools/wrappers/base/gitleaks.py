"""Shared base class for gitleaks local and docker wrappers."""

import os
import tempfile
from pathlib import Path
from typing import Any

from core.config.schemas import build_excluded_dirs
from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface
from infrastructure.tools.parsers.gitleaks import combine_gitleaks_results


class BaseGitleaksTool(ToolInterface):
    _candidate_commands: list[str] = ["gitleaks"]
    _command_entry_type: str = "repo"
    _last_ignore_path: str | None = None

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
    def timeout(self) -> int:
        return 7200  # Large repos with deep history may be slow

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        exclude = build_excluded_dirs(context.repo)

        shared_kwargs: dict[str, object] = {"repo_path": repo_path}
        # Always exclude .git because the dir scan is a plain filesystem walk
        # that would crawl .git/objects/pack (potentially GBs of binary data).
        # The git pass handles history via git's own traversal.
        all_excludes = [".git"] + exclude
        patterns = "\n".join(f"**/{d}" for d in all_excludes) + "\n"
        if context.repo.docker_path and context.repo.path:
            # Docker mode: write to local repo path (already mounted in container).
            # The file is overwritten on each scan; it is not committed.
            ignore_file = Path(context.repo.path) / ".tally_gitleaksignore"
            ignore_file.write_text(patterns)
            container_ignore = f"{context.repo.docker_path}/.tally_gitleaksignore"
            shared_kwargs["gitleaks_ignore_path"] = container_ignore
        else:
            # Local mode: write to a temp file.
            fd, tmp = tempfile.mkstemp(suffix=".gitleaksignore", prefix="tally_")
            with os.fdopen(fd, "w") as f:
                f.write(patterns)
            self._last_ignore_path = tmp
            shared_kwargs["gitleaks_ignore_path"] = tmp

        return [
            ExecutionPass(
                label_suffix=f"{context.repo.name}_dir",
                kwargs={**shared_kwargs, "scan_type": "dir"},
            ),
            ExecutionPass(
                label_suffix=f"{context.repo.name}_git",
                kwargs={**shared_kwargs, "scan_type": "git"},
            ),
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        """Combine dir-scan and git-scan passes into a single result."""
        if self._last_ignore_path is not None:
            Path(self._last_ignore_path).unlink(missing_ok=True)
            self._last_ignore_path = None
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
        return result

"""composer-audit wrapper for PHP dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path
from typing import Any

from ...base import ToolResult, ToolWrapper
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.composer_audit_parser import (
    parse_composer_audit_json,
    parse_composer_audit_json_string,
)


class ComposerAuditWrapper(ToolInterface, ToolWrapper):
    def __init__(self, config=None) -> None:
        pass

    @property
    def name(self) -> str:
        return "composer-audit"

    @property
    def command(self) -> str:
        return "composer"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "PHP dependency vulnerability scanner using Packagist security advisories"
        )

    @property
    def scan_segment(self) -> str:
        return "sca"

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return ["php"]

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def check_available(self) -> bool:
        return shutil.which("composer") is not None

    def build_command(self, **kwargs) -> list[str]:
        """Build the composer audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
                             Must contain a composer.json file.

        Note:
            composer audit must run in the directory containing composer.json.
            The executor must be called with ``cwd=repo_path`` so the
            subprocess runs inside the repository directory.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for composer-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        if not (repo / "composer.json").exists():
            raise ValueError(f"No composer.json found in {repo_path!r}")

        return ["composer", "audit", "--format=json"]

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse composer audit JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_composer_audit_json(json_path)
        return parse_composer_audit_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
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

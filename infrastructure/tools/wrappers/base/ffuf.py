"""Shared base class for ffuf local and docker wrappers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface


def resolve_wordlists(configured_paths: list[str]) -> list[str]:
    """Return valid wordlist paths from config, env, or system defaults.

    If any configured path exists on disk, return only the valid
    configured paths. Otherwise fall back to FFUF_WORDLIST env var,
    then common system locations.
    """
    valid = [p for p in configured_paths if p and Path(p).exists()]
    if valid:
        return valid

    env_wordlist = os.environ.get("FFUF_WORDLIST")
    if env_wordlist and Path(env_wordlist).exists():
        return [env_wordlist]

    common_paths = [
        "/usr/share/seclists/Discovery/Web-Content/directory-list-2.3-medium.txt",
        "/usr/share/wordlists/dirb/common.txt",
        "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
    ]
    for path_str in common_paths:
        if Path(path_str).exists():
            return [path_str]

    return []


class BaseFFufTool(ToolInterface):
    """Base class shared by local and Docker ffuf wrappers.

    ffuf is a fast web fuzzer that brute-forces URLs using wordlists to
    discover hidden files, directories, and parameters.
    """

    _candidate_commands: list[str] = ["ffuf"]
    _command_entry_type: str = "api"

    @property
    def name(self) -> str:
        return "ffuf"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "Fast web fuzzer for discovering hidden files, directories, "
            "and parameters via wordlist-based brute-force"
        )

    @property
    def scan_segment(self) -> str:
        return "web"

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
        return True

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
        assert context.service is not None

        wordlists = resolve_wordlists(context.tool_config.ffuf_wordlist_paths)
        if not wordlists:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "ffuf: no wordlist found; install SecLists or set FFUF_WORDLIST"
            )
            return []

        base_url = context.service.base_urls[0]
        passes: list[ExecutionPass] = []

        for wordlist in wordlists:
            wl_name = Path(wordlist).stem
            output_file = self._get_output_file(context)
            passes.append(
                ExecutionPass(
                    label_suffix=f"{context.repo.name}_{wl_name}",
                    kwargs={
                        "base_url": base_url,
                        "wordlist": wordlist,
                        "output_file": output_file,
                    },
                ),
            )

        return passes

    @staticmethod
    def _get_output_file(context: ExecutionContext) -> str:
        from datetime import UTC, datetime
        from pathlib import Path

        from core.project_paths import ProjectPaths

        paths = ProjectPaths.from_canonical(
            str(Path(context.base_path).resolve()), context.project_name
        )
        output_dir = paths.tool_output_dir("ffuf")
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        repo_name = context.repo.name if context.repo else "scan"
        return str(output_dir / f"{repo_name}_{ts}.json")

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        if len(pass_results) == 1:
            return pass_results[0]

        seen: set[tuple[str, int]] = set()
        merged_findings: list[dict[str, Any]] = []

        for result in pass_results:
            parsed = result.parsed_data or {}
            for finding in parsed.get("findings", []):
                key = (
                    finding.get("url", ""),
                    finding.get("status", 0),
                )
                if key not in seen:
                    seen.add(key)
                    merged_findings.append(finding)

        combined_files: dict[str, Path] = {}
        for i, result in enumerate(pass_results):
            for k, v in result.output_files.items():
                combined_files[f"pass{i}_{k}"] = v

        total_duration = sum(r.duration_seconds for r in pass_results)
        combined_output = "\n".join(r.output or "" for r in pass_results)

        return ToolResult(
            tool_name="ffuf",
            success=any(r.success for r in pass_results),
            output=combined_output,
            parsed_data={
                "findings": merged_findings,
                "summary": {
                    "total_findings": len(merged_findings),
                },
            },
            output_files=combined_files,
            timestamp=pass_results[0].timestamp,
            duration_seconds=total_duration,
        )

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", len(parsed_data.get("findings", [])))

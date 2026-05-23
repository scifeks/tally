"""Shared base class for nuclei local and docker wrappers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface


class BaseNucleiTool(ToolInterface):
    """Base class shared by local and Docker nuclei wrappers.

    Nuclei is a template-based vulnerability scanner targeting live URLs
    using two pass modes: automatic (technology fingerprinting) and DAST
    (fuzzing). Consumes URLs from the URL inventory pipeline.
    """

    _candidate_commands: list[str] = ["nuclei"]
    _command_entry_type: str = "api"

    @property
    def name(self) -> str:
        return "nuclei"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "Nuclei template-based vulnerability scanner; uses automatic "
            "technology fingerprinting and DAST fuzzing against live URLs"
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
        return False

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
        """Return two ExecutionPass objects: automatic and DAST modes.

        Rebuilds URL artifacts JIT from the inventory; falls back to base_url
        when no inventory exists.
        """
        from application.url_inventory.jit import jit_rebuild_artifacts
        from infrastructure.store.connection import ConnectionFactory
        from infrastructure.store.repositories.url_findings import (
            UrlFindingRepository,
        )

        assert context.repo is not None
        assert context.service is not None
        repo = context.repo

        paths = ProjectPaths.from_canonical(
            str(Path(context.base_path).resolve()), context.project_name
        )
        output_dir = paths.tool_output_dir("nuclei")
        output_dir.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_file_auto = str(output_dir / f"{repo.name}_{ts}_auto.json")
        output_file_dast = str(output_dir / f"{repo.name}_{ts}_dast.json")

        repo_path = context.registry.get_service_path(
            self.name, context.service, repo.path
        )
        shared_kwargs: dict[str, Any] = {"base_url": context.service.base_urls[0]}

        seeds_path, _oas3_path = jit_rebuild_artifacts(
            context.base_path,
            context.project_name,
            repo,
            url_finding_repo=url_repo,
        )
        if seeds_path:
            shared_kwargs["urls_file"] = seeds_path

        custom_template_dir = Path(repo_path) / ".nuclei"
        if custom_template_dir.is_dir():
            shared_kwargs["custom_template_dir"] = str(custom_template_dir)

        return [
            ExecutionPass(
                label_suffix=f"{repo.name}_auto",
                kwargs={
                    **shared_kwargs,
                    "pass_type": "automatic",
                    "output_file": output_file_auto,
                },
            ),
            ExecutionPass(
                label_suffix=f"{repo.name}_dast",
                kwargs={
                    **shared_kwargs,
                    "pass_type": "dast",
                    "output_file": output_file_dast,
                },
            ),
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        """Combine automatic and DAST pass results with deduplication.

        Combines findings from both passes and deduplicates by template ID
        and matched URL to produce a single result.
        """
        auto_result, dast_result = pass_results[0], pass_results[1]
        auto_data = auto_result.parsed_data or {}
        dast_data = dast_result.parsed_data or {}

        auto_findings = auto_data.get("findings", [])
        dast_findings = dast_data.get("findings", [])

        # Deduplicate by fingerprint: nuclei|<template-id>|<matched-at>
        seen: dict[str, dict[str, Any]] = {}
        for finding in auto_findings:
            key = self._fingerprint_finding(finding)
            if key not in seen:
                seen[key] = finding

        for finding in dast_findings:
            key = self._fingerprint_finding(finding)
            if key not in seen:
                seen[key] = finding

        combined_findings = list(seen.values())

        combined_data = {
            "findings": combined_findings,
            "summary": {"total_findings": len(combined_findings)},
        }

        combined_files = {f"auto_{k}": v for k, v in auto_result.output_files.items()}
        combined_files.update(
            {f"dast_{k}": v for k, v in dast_result.output_files.items()}
        )

        return ToolResult(
            tool_name="nuclei",
            success=auto_result.success or dast_result.success,
            output=(auto_result.output or "") + "\n" + (dast_result.output or ""),
            parsed_data=combined_data,
            output_files=combined_files,
            timestamp=auto_result.timestamp,
            duration_seconds=(
                auto_result.duration_seconds + dast_result.duration_seconds
            ),
        )

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", len(parsed_data.get("findings", [])))

    @staticmethod
    def _fingerprint_finding(finding: dict[str, Any]) -> str:
        """Generate a fingerprint key for deduplication."""
        template_id = str(finding.get("template_id", ""))
        matched_at = str(finding.get("matched_at", ""))
        return f"nuclei|{template_id}|{matched_at}"

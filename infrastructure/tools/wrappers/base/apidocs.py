"""Base class for the apidocs agentic endpoint discovery tool.

Orchestrates the 4-stage apidocs pipeline (recon, discovery, enrich,
assemble) via Claude Code agents. Produces an OAS3 JSON file that the
URL inventory ingests for downstream DAST tools.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.base import ToolResult
from domain.tools.interface import (
    ExecutionContext,
    ExecutionPass,
    ToolInterface,
)

logger = logging.getLogger(__name__)

_INFRA_DIR = Path(__file__).resolve().parents[3]
_APIDOCS_PKG = _INFRA_DIR / "apidocs"
_ROUTE_ID_SCRIPT = _APIDOCS_PKG / "route_id.py"


class BaseApidocsTool(ToolInterface):
    """Base class for the apidocs local wrapper."""

    _candidate_commands: list[str] = ["claude"]

    @property
    def name(self) -> str:
        return "apidocs"

    @property
    def scan_segment(self) -> str:
        return "web"

    @property
    def skip(self) -> bool:
        return True

    @property
    def is_discovery_tool(self) -> bool:
        return True

    @property
    def should_visualize(self) -> bool:
        return False

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
    def timeout(self) -> int | None:
        return 3600

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.repo.path

        output_dir = ProjectPaths.from_canonical(
            context.base_path, context.project_name
        ).tool_output_dir("apidocs")
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        self._output_file = str(output_dir / f"{context.repo.name}_{ts}_oas3.json")
        self._repo_path = repo_path

        self._setup_route_id_symlink(repo_path)

        shared = {
            "repo_path": repo_path,
            "output_file": self._output_file,
        }
        return [
            ExecutionPass(
                label_suffix="recon",
                kwargs={**shared, "stage": "recon"},
                cwd=repo_path,
            ),
            ExecutionPass(
                label_suffix="discovery",
                kwargs={**shared, "stage": "discovery"},
                cwd=repo_path,
            ),
            ExecutionPass(
                label_suffix="enrich",
                kwargs={**shared, "stage": "enrich"},
            ),
            ExecutionPass(
                label_suffix="assemble",
                kwargs={**shared, "stage": "assemble"},
                cwd=repo_path,
            ),
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        self._cleanup_route_id_symlink()

        if not pass_results:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                parsed_data={"error": "no passes ran", "endpoints": []},
                output_files={},
                timestamp=ToolResult.now_iso(),
                duration_seconds=0,
            )

        last = pass_results[-1]
        total_duration = sum(r.duration_seconds for r in pass_results)
        success = all(r.success for r in pass_results)

        return ToolResult(
            tool_name=self.name,
            success=success,
            output=last.output,
            parsed_data=last.parsed_data,
            output_files=dict(last.output_files),
            timestamp=last.timestamp,
            duration_seconds=total_duration,
            finding_count=last.finding_count,
        )

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        return len(parsed_data.get("endpoints", []))

    def _setup_route_id_symlink(self, repo_path: str) -> None:
        scripts_dir = Path(repo_path) / "scripts"
        link_path = scripts_dir / "route_id.py"
        self._symlink_path = link_path
        self._created_scripts_dir = False
        if not scripts_dir.exists():
            scripts_dir.mkdir(parents=True, exist_ok=True)
            self._created_scripts_dir = True
        if not link_path.exists():
            link_path.symlink_to(_ROUTE_ID_SCRIPT.resolve())

    def _cleanup_route_id_symlink(self) -> None:
        link = getattr(self, "_symlink_path", None)
        if link is not None and link.is_symlink():
            link.unlink()
        if getattr(self, "_created_scripts_dir", False):
            scripts_dir = link.parent if link else None
            if (
                scripts_dir is not None
                and scripts_dir.exists()
                and not any(scripts_dir.iterdir())
            ):
                scripts_dir.rmdir()

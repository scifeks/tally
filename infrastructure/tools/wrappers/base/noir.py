"""Shared base class for the OWASP Noir endpoint-discovery wrapper.

Noir is a Crystal binary (``/usr/bin/noir``) that performs static analysis
on source code and emits discovered API endpoints as an OAS3 JSON document.
It is a **pre-DAST** step: its output feeds into ZAP via the
``-openapifile`` flag rather than being a vulnerability scanner itself.

Architecture note
-----------------
Because Noir writes its report to a file specified by ``-o`` (not to stdout),
the concrete ``NoirLocalTool`` subclass overrides ``parse_output`` exactly as
``GitleaksLocalTool`` does for its JSON report path.  The base class
``parse_output`` is a safe fallback that handles the stdout path in case
a future Docker wrapper captures output differently.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface
from infrastructure.tools.parsers.noir_parser import (
    parse_noir_json,
    parse_noir_json_string,
)


class BaseNoirTool(ToolInterface):
    """Base class shared by local (and any future Docker) Noir wrappers."""

    _candidate_commands: list[str] = ["noir"]
    _command_entry_type: str = "repo"

    # ------------------------------------------------------------------
    # ToolInterface — identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "noir"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "OWASP Noir — attack surface detector that discovers API endpoints "
            "by static analysis and emits an OAS3 spec for downstream DAST."
        )

    @property
    def scan_segment(self) -> str:
        return "web"

    # ------------------------------------------------------------------
    # ToolInterface — behaviour flags
    # ------------------------------------------------------------------

    @property
    def skip(self) -> bool:
        # Noir produces endpoint *metadata*, not triage-able vulnerability
        # findings.  Rows are stored as informational records; triage is skipped.
        return True

    @property
    def findings_exit_ok(self) -> bool:
        # Noir exits 0 regardless of how many endpoints it finds.
        return True

    @property
    def language_gates(self) -> list[str]:
        # Language-agnostic — scans any source tree.
        return []

    @property
    def requires_base_urls(self) -> bool:
        # Noir analyses source code; it does not need a live URL.
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

    # ------------------------------------------------------------------
    # ToolInterface — parse + execute
    # ------------------------------------------------------------------

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse Noir output.

        Prefers the saved stdout file (for wrappers that capture stdout);
        falls back to the raw output string.  Local subclass overrides this
        to prefer the ``-o`` report file.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_noir_json(json_path)
        return parse_noir_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass that scans the repo source tree."""
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        output_dir = (
            Path(context.base_path)
            / "projects"
            / context.project_name
            / "tool_outputs"
            / "noir"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_file = str(output_dir / f"{context.repo.name}_{ts}_oas3.json")
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={
                    "source_path": repo_path,
                    "output_file": output_file,
                },
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        return parsed_data.get("summary", {}).get(
            "total_endpoints", len(parsed_data.get("endpoints", []))
        )

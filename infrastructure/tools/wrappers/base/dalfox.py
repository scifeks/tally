"""Shared base class for DalFox local and docker wrappers."""

from __future__ import annotations

from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ToolInterface


class BaseDalFoxTool(ToolInterface):
    """Base class shared by local and Docker DalFox wrappers.

    Detects XSS in JavaScript-heavy applications and SPAs by rendering
    pages with headless Chrome. Requires base_urls configured on the
    repository; scans are skipped when none are present.
    """

    _candidate_commands: list[str] = ["dalfox"]
    _command_entry_type: str = "api"

    @property
    def name(self) -> str:
        return "dalfox"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "DalFox XSS scanner; uses headless Chrome to detect cross-site "
            "scripting vulnerabilities in SPAs and JavaScript-heavy applications"
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
        # DalFox exits non-zero when vulnerabilities are found.
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

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", len(parsed_data.get("findings", [])))

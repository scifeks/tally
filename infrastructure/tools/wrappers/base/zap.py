"""Shared base class for ZAP local and docker wrappers."""

from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ToolInterface


class BaseZapTool(ToolInterface):
    _candidate_commands: list[str] = ["zap.sh", "zap-cli", "zaproxy"]
    _command_entry_type: str = "api"

    @property
    def name(self) -> str:
        return "zap"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "OWASP ZAP dynamic web application security scanner"

    @property
    def scan_segment(self) -> str:
        return "web"

    @property
    def skip(self) -> bool:
        return False

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

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        result = summary.get("total_alerts", len(parsed_data.get("alerts", [])))
        # TODO: revisit when normalized schema is introduced
        return result

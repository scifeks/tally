"""Burp Suite tool wrapper for registry registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.tools.interface import ToolInterface, TransportType
from infrastructure.tools.burp.probe import probe_burp_availability

if TYPE_CHECKING:
    from pathlib import Path

    from core.config.schemas.burp_config import BurpConfig


class BurpToolWrapper(ToolInterface):
    """Registration-only wrapper for Burp Suite.

    HTTP-transport tools do not use execution passes.
    Execution routes through HttpToolRunner.
    """

    def __init__(self, *, burp_config: BurpConfig) -> None:
        self._config = burp_config

    @property
    def name(self) -> str:
        return "burp"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Web vulnerability scanner using crawl-and-audit"

    @property
    def scan_segment(self) -> str:
        return "web"

    @property
    def transport(self) -> TransportType:
        return TransportType.HTTP

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
        return []

    @property
    def command(self) -> str:
        return ""

    @property
    def supported_languages(self) -> list[str] | None:
        return None

    def check_available(self) -> bool:
        result = probe_burp_availability(self._config)
        return result is True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs: Any) -> list[str]:
        raise NotImplementedError("HTTP-transport tool; use HttpToolRunner")

    def parse_output(
        self,
        output: str,
        files: dict[str, Path],
    ) -> dict[str, Any]:
        raise NotImplementedError("HTTP-transport tool; use HttpToolRunner")

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", 0)

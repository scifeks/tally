"""Shared base class for the Katana runtime crawler wrapper.

Katana (github.com/projectdiscovery/katana) is a headless-capable web
crawler from ProjectDiscovery. It performs runtime URL discovery by following
links, extracting XHR endpoints, and optionally rendering JavaScript via a
headless browser, then emits results as JSONL.

Role in the pipeline
---------------------
Katana is a **discovery** tool, not a vulnerability scanner.  It runs before
DalFox, XSStrike, and ZAP within the ``web`` segment so that DAST tools can
consume its OAS3 output via ``_build_seeds_from_katana`` or
``_find_katana_oas3`` helpers.

Katana is the primary discovery tool for repositories where Noir is skipped
(e.g. Node.js apps or repos using unsupported frameworks like aiohttp).
"""

from __future__ import annotations

from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ToolInterface


class BaseKatanaTool(ToolInterface):
    """Base class shared by local (and any future Docker) Katana wrappers."""

    _candidate_commands: list[str] = ["katana"]
    _command_entry_type: str = "api"

    @property
    def name(self) -> str:
        return "katana"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "ProjectDiscovery Katana headless crawler for runtime URL and "
            "endpoint discovery; feeds DAST tools via OAS3 output."
        )

    @property
    def scan_segment(self) -> str:
        return "web"

    @property
    def is_discovery_tool(self) -> bool:
        return True

    @property
    def skip(self) -> bool:
        # Katana produces endpoint metadata, not triage-able findings.
        return True

    @property
    def should_visualize(self) -> bool:
        return False

    @property
    def findings_exit_ok(self) -> bool:
        # Katana exits 0 on success regardless of how many endpoints it finds.
        return False

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def requires_base_urls(self) -> bool:
        # Katana crawls a live URL; it requires base_urls to be configured.
        return True

    @property
    def timeout(self) -> int:
        # Katana's native -ct ceiling is 900 s; allow extra slack for Chrome
        # startup/shutdown before the executor hard-kills the process group.
        return 1200

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
        return summary.get("total_endpoints", len(parsed_data.get("endpoints", [])))

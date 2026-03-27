"""Shared stub ToolHandler implementations for ingestor tests."""

from __future__ import annotations

from domain.tools.base import ToolResult


class _StubBuilder:
    tool_name = "semgrep"
    domain = "code"
    segment = "sast"
    non_enriched_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {}
    should_enrich = False
    enrichment_fields = None

    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        return list(self._rows)

    def render(self, row: dict) -> str:
        return "stub"


class _NetworkStubBuilder:
    """Stub for a non-code-domain tool (e.g. nmap)."""

    tool_name = "nmap"
    domain = "network"
    segment = "network"
    non_enriched_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {}
    should_enrich = False
    enrichment_fields = None

    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        return list(self._rows)

    def render(self, row: dict) -> str:
        return "stub"

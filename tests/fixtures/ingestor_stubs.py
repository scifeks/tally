"""Shared stub ChunkBuilder implementations for ingestor tests."""

from __future__ import annotations

from typing import Any

from domain.tools.base import ToolResult


class _StubBuilder:
    tool_name = "semgrep"
    domain = "code"
    segment = "sast"
    non_enriched_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {}
    should_enrich = False

    def __init__(
        self, chunks: list[tuple[str, dict[str, Any], str]] | None = None
    ) -> None:
        self._chunks = chunks or []

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return list(self._chunks)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return str(finding)


class _NetworkStubBuilder:
    """Stub for a non-code-domain tool (e.g. nmap)."""

    tool_name = "nmap"
    domain = "network"
    segment = "network"
    non_enriched_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {}
    should_enrich = False

    def __init__(
        self, chunks: list[tuple[str, dict[str, Any], str]] | None = None
    ) -> None:
        self._chunks = chunks or []

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return list(self._chunks)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return str(finding)

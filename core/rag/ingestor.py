"""Finding ingestion pipeline — converts ToolResult output into ChromaDB documents."""

import logging
from collections.abc import Callable
from typing import Any, Protocol

from core.tools.base import ToolResult

from .chunks import (
    ComposerAuditChunkBuilder,
    GitleaksChunkBuilder,
    NmapChunkBuilder,
    NpmAuditChunkBuilder,
    OsvScannerChunkBuilder,
    PipAuditChunkBuilder,
    SemgrepChunkBuilder,
    ZapChunkBuilder,
)
from .engine import RAGEngine

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# ChunkBuilder Protocol
# ------------------------------------------------------------------


class ChunkBuilder(Protocol):
    tool_name: str

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]: ...

    def fingerprint_key(self, finding: dict[str, Any]) -> str: ...


# ------------------------------------------------------------------
# Builder registry helpers
# ------------------------------------------------------------------


def _default_builders() -> dict[str, ChunkBuilder]:
    builders: list[ChunkBuilder] = [
        NmapChunkBuilder(),
        SemgrepChunkBuilder(),
        OsvScannerChunkBuilder(),
        PipAuditChunkBuilder(),
        NpmAuditChunkBuilder(),
        ComposerAuditChunkBuilder(),
        GitleaksChunkBuilder(),
        ZapChunkBuilder(),
    ]
    return {b.tool_name: b for b in builders}


def get_fingerprint_registry() -> dict[str, Callable[[dict[str, Any]], str]]:
    return {
        name: builder.fingerprint_key for name, builder in _default_builders().items()
    }


# ------------------------------------------------------------------
# FindingIngestor
# ------------------------------------------------------------------


class FindingIngestor:
    """Ingests tool findings into the project's ChromaDB collection.

    Uses delete-insert: stale findings for a tool/profile are removed before
    new ones are added, so re-running a scan never produces duplicates.

    Document ID format::

        <tool>_<profile>_<type>_<indices>_<compact_utc>
        nmap_webservers_host_0_20240228T143022
    """

    def __init__(
        self,
        rag_engine: RAGEngine,
        project_name: str,
        builders: dict[str, ChunkBuilder] | None = None,
    ) -> None:
        self._engine = rag_engine
        self.project_name = project_name
        self._builders: dict[str, ChunkBuilder] = (
            builders if builders is not None else _default_builders()
        )

    def ingest_tool_output(
        self,
        tool_result: ToolResult,
        profile: str | None = None,
    ) -> list[str]:
        """Index a tool's findings into ChromaDB, replacing stale entries."""
        tool = tool_result.tool_name
        effective_profile = profile or "manual"

        if not tool_result.success or tool_result.parsed_data is None:
            logger.warning(
                "Skipping ingestion for %s/%s: "
                "tool did not succeed or produced no parsed data",
                tool,
                effective_profile,
            )
            return []

        if "error" in tool_result.parsed_data:
            logger.warning(
                "Skipping ingestion for %s/%s: parse error — %s",
                tool,
                effective_profile,
                tool_result.parsed_data["error"],
            )
            return []

        deleted = self._engine.delete_findings(tool, effective_profile)
        if deleted:
            logger.debug(
                "Deleted %d stale findings for %s/%s", deleted, tool, effective_profile
            )

        chunks = self._build_chunks(tool_result, effective_profile)

        if not chunks:
            logger.info("No findings to ingest for %s/%s", tool, effective_profile)
            return []

        texts, metadatas, ids = zip(*chunks)
        self._engine.add_documents(list(texts), list(metadatas), list(ids))
        logger.info(
            "Ingested %d documents for %s/%s", len(chunks), tool, effective_profile
        )
        return list(ids)

    def _build_chunks(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Dispatch to the registered ChunkBuilder for the tool."""
        tool = tool_result.tool_name
        builder = self._builders.get(tool)
        if builder is None:
            logger.debug(
                "No chunk builder registered for tool '%s'; skipping ingestion", tool
            )
            return []
        return builder.build(tool_result, profile)

    def _process_finding(
        self,
        finding: dict[str, Any],
        tool_name: str,
        profile: str,
    ) -> tuple[str, dict[str, Any]]:
        """Convert a single finding dict to a (text, metadata) pair (stub)."""
        text = str(finding)
        metadata: dict[str, Any] = {
            "tool": tool_name,
            "profile": profile,
            "finding_type": finding.get("type", "unknown"),
            "timestamp": RAGEngine.now_iso(),
        }
        return text, metadata

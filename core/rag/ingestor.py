"""Finding ingestion pipeline — converts ToolResult output into ChromaDB documents."""

import importlib
import inspect
import logging
from collections.abc import Callable
from typing import Any, Protocol

from core.tools.base import ToolResult

from .engine import RAGEngine

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# ChunkBuilder Protocol
# ------------------------------------------------------------------


class ChunkBuilder(Protocol):
    tool_name: str
    domain: str
    non_enriched_fields: frozenset[str]
    type_flags: dict[str, set[str]]
    should_enrich: bool

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]: ...

    def fingerprint_key(self, finding: dict[str, Any]) -> str: ...


# ------------------------------------------------------------------
# ChunkBuilderFactory
# ------------------------------------------------------------------


class ChunkBuilderFactory:
    @staticmethod
    def load(tool_name: str) -> ChunkBuilder | None:
        """Load and instantiate the chunk builder for tool_name, or None."""
        stem = tool_name.replace("-", "_")
        try:
            module = importlib.import_module(f"core.rag.chunks.{stem}")
        except ImportError:
            logger.debug("No chunk builder module for tool %r", tool_name)
            return None
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj.__module__ == module.__name__
                and getattr(obj, "tool_name", None) == tool_name
            ):
                return obj()
        logger.debug("No ChunkBuilder class found in module for tool %r", tool_name)
        return None


# ------------------------------------------------------------------
# Builder registry helpers
# ------------------------------------------------------------------


def _default_builders() -> dict[str, ChunkBuilder]:
    """Discover all chunk builders by scanning the chunks package directory."""
    from pathlib import Path

    result: dict[str, ChunkBuilder] = {}
    chunks_dir = Path(__file__).parent / "chunks"
    for module_file in sorted(chunks_dir.glob("*.py")):
        if module_file.name.startswith("_") or module_file.stem == "sca":
            continue
        tool_name = module_file.stem.replace("_", "-")
        builder = ChunkBuilderFactory.load(tool_name)
        if builder is not None:
            result[builder.tool_name] = builder
    return result


def get_fingerprint_registry() -> dict[str, Callable[[dict[str, Any]], str]]:
    return {name: b.fingerprint_key for name, b in _default_builders().items()}


def get_tool_domain(tool_name: str) -> str | None:
    """Return the domain ('code', 'web', 'network') for a tool, or None."""
    builder = ChunkBuilderFactory.load(tool_name)
    return builder.domain if builder is not None else None


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

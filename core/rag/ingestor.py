"""Finding ingestion pipeline — converts ToolResult output into ChromaDB documents."""

import importlib
import inspect
import logging
from collections.abc import Callable
from typing import Any, Protocol

from core.config.schemas import Repository
from domain.tools.base import ToolResult

from .engine import RAGEngine

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# ChunkBuilder Protocol
# ------------------------------------------------------------------


class ChunkBuilder(Protocol):
    tool_name: str
    domain: str
    segment: str
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


def _is_test_path(rel_path: str, test_dirs: list[str]) -> bool:
    """Return True if rel_path falls inside one of the given test dirs.

    rel_path must start with '/': e.g. '/tests/foo.py'.
    test_dirs are bare names or relative sub-paths: e.g. ['tests', 'spec'].
    """
    for td in test_dirs:
        prefix = f"/{td}/"
        if rel_path.startswith(prefix) or rel_path == f"/{td}":
            return True
    return False


def _normalize_path(file_path: str, repos: list[Repository]) -> tuple[str, str | None]:
    """Return (relative_path, repo_name) for file_path.

    If file_path starts with repo.path, strip that prefix.
    If no repo matches, return (file_path, None) unchanged.
    repo_name is None when no match found or file_path is empty.
    """
    if not file_path:
        return (file_path, None)
    for repo in repos:
        if repo.path and file_path.startswith(repo.path):
            rel = "/" + file_path[len(repo.path) :].lstrip("/")
            return (rel, repo.name)
    return (file_path, None)


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
        repositories: list[Repository] | None = None,
    ) -> None:
        self._engine = rag_engine
        self.project_name = project_name
        self._builders: dict[str, ChunkBuilder] = (
            builders if builders is not None else _default_builders()
        )
        self._repositories = repositories
        self._repo_test_dirs: dict[str, list[str]] = {
            r.name: r.test_dirs for r in (repositories or []) if r.test_dirs
        }

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

        raw_chunks = builder.build(tool_result, profile)

        if self._repositories is None:
            return raw_chunks

        chunks: list[tuple[str, dict[str, Any], str]] = []
        for text, meta, doc_id in raw_chunks:
            file_path: str = meta.get("file_path", "") or ""
            rel_path, repo_name = _normalize_path(file_path, self._repositories)
            meta["file_path"] = rel_path
            if repo_name is not None:
                meta["repo"] = repo_name

            if builder.domain == "code" and not rel_path:
                logger.error(
                    "Excluding chunk with missing file path: tool=%s rule_id=%s",
                    tool,
                    meta.get("rule_id", ""),
                )
                continue

            if builder.domain == "code" and repo_name is not None and rel_path:
                _tdirs = self._repo_test_dirs.get(repo_name, [])
                if _tdirs and _is_test_path(rel_path, _tdirs):
                    logger.debug(
                        "Excluding test-dir chunk: tool=%s path=%s",
                        tool,
                        rel_path,
                    )
                    continue

            chunks.append((text, meta, doc_id))

        return chunks

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

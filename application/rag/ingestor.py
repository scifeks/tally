"""Finding ingestion pipeline — converts ToolResult output into ChromaDB documents."""

import importlib
import inspect
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from core.config.schemas import Repository
from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from .engine import RAGEngine

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# ToolHandler Protocol
# ------------------------------------------------------------------


class ToolHandler(Protocol):
    tool_name: str
    domain: str
    segment: str
    non_enriched_fields: frozenset[str]
    type_flags: dict[str, set[str]]
    should_enrich: bool
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] | None

    def normalize(self, result: ToolResult, profile: str) -> list[dict]: ...

    def render(self, row: dict) -> str: ...


# ------------------------------------------------------------------
# ToolHandlerFactory
# ------------------------------------------------------------------


class ToolHandlerFactory:
    @staticmethod
    def load(tool_name: str) -> ToolHandler | None:
        """Load and instantiate the tool handler for tool_name, or None."""
        stem = tool_name.replace("-", "_")
        try:
            module = importlib.import_module(f"application.rag.chunks.{stem}")
        except ImportError:
            logger.debug("No tool handler module for tool %r", tool_name)
            return None
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj.__module__ == module.__name__
                and getattr(obj, "tool_name", None) == tool_name
            ):
                return obj()
        logger.debug("No ToolHandler class found in module for tool %r", tool_name)
        return None


# Backward-compat alias — enrichment.py imports this name and must not be modified.
ChunkBuilderFactory = ToolHandlerFactory


# ------------------------------------------------------------------
# Handler registry helpers
# ------------------------------------------------------------------


def _default_builders() -> dict[str, ToolHandler]:
    """Discover all tool handlers by scanning the chunks package directory."""
    from pathlib import Path

    result: dict[str, ToolHandler] = {}
    chunks_dir = Path(__file__).parent / "chunks"
    for module_file in sorted(chunks_dir.glob("*.py")):
        if module_file.name.startswith("_") or module_file.stem == "sca":
            continue
        tool_name = module_file.stem.replace("_", "-")
        handler = ToolHandlerFactory.load(tool_name)
        if handler is not None:
            result[handler.tool_name] = handler
    return result


def get_tool_domain(tool_name: str) -> str | None:
    """Return the domain ('code', 'web', 'network') for a tool, or None."""
    handler = ToolHandlerFactory.load(tool_name)
    return handler.domain if handler is not None else None


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


def _relativize_path(
    file_path: str, repo_name: str, repos: list[Repository] | None
) -> str:
    """Strip repo's path prefix from file_path when it matches.

    Used when repo identity is already known from execution context.
    Returns file_path unchanged when repos is None, the named repo has no
    path, the path doesn't match (e.g. gitleaks relative paths), or
    file_path is empty.
    """
    if not file_path or repos is None:
        return file_path
    for repo in repos:
        if repo.name == repo_name and repo.path and file_path.startswith(repo.path):
            return "/" + file_path[len(repo.path) :].lstrip("/")
    return file_path


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
        builders: dict[str, ToolHandler] | None = None,
        repositories: list[Repository] | None = None,
        repo_name: str | None = None,
    ) -> None:
        self._engine = rag_engine
        self.project_name = project_name
        self._builders: dict[str, ToolHandler] = (
            builders if builders is not None else _default_builders()
        )
        self._repositories = repositories
        self._repo_name = repo_name
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
        """Dispatch to the registered ToolHandler for the tool."""
        tool = tool_result.tool_name
        handler = self._builders.get(tool)
        if handler is None:
            logger.debug(
                "No tool handler registered for tool '%s'; skipping ingestion", tool
            )
            return []

        raw_rows: list[dict] = handler.normalize(tool_result, profile)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        if self._repositories is None:
            return [
                (handler.render(row), row, f"{tool}_{profile}_{i}_{ts_compact}")
                for i, row in enumerate(raw_rows)
            ]

        chunks: list[tuple[str, dict[str, Any], str]] = []
        for i, meta in enumerate(raw_rows):
            file_path: str = meta.get("file_path", "") or ""
            if self._repo_name is not None:
                repo_name: str | None = self._repo_name
                rel_path = _relativize_path(
                    file_path, self._repo_name, self._repositories
                )
            else:
                rel_path, repo_name = _normalize_path(file_path, self._repositories)
            meta["file_path"] = rel_path
            if repo_name is not None:
                meta["repo"] = repo_name

            if handler.domain == "code" and not rel_path:
                logger.error(
                    "Excluding chunk with missing file path: tool=%s rule_id=%s",
                    tool,
                    meta.get("rule_id", ""),
                )
                continue

            if handler.domain == "code" and repo_name is not None and rel_path:
                _tdirs = self._repo_test_dirs.get(repo_name, [])
                if _tdirs and _is_test_path(rel_path, _tdirs):
                    logger.debug(
                        "Excluding test-dir chunk: tool=%s path=%s",
                        tool,
                        rel_path,
                    )
                    continue

            doc_id = f"{tool}_{profile}_{i}_{ts_compact}"
            chunks.append((handler.render(meta), meta, doc_id))

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

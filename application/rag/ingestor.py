"""Finding ingestion pipeline — ToolHandler protocol and path-normalisation helpers."""

import importlib
import inspect
import logging
from typing import Protocol

from core.config.schemas import Repository
from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

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


# ------------------------------------------------------------------
# Handler registry helpers
# ------------------------------------------------------------------


def get_tool_domain(tool_name: str) -> str | None:
    """Return the domain ('code', 'web', 'network') for a tool, or None."""
    handler = ToolHandlerFactory.load(tool_name)
    return handler.domain if handler is not None else None


def is_test_path(rel_path: str, test_dirs: list[str]) -> bool:
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


def normalize_file_path(
    file_path: str,
    repositories: list[Repository],
    repo_name: str | None = None,
) -> tuple[str, str | None] | None:
    """Normalize file_path relative to repositories.

    Returns (relative_path, repo_name) or None when file_path is empty.
    When repo_name is provided, strips that repo's path prefix; otherwise
    finds the best-matching repo from the list.
    """
    if not file_path:
        return None
    if repo_name is not None:
        rel = _relativize_path(file_path, repo_name, repositories)
        return (rel, repo_name)
    return _normalize_path(file_path, repositories)


def filter_code_rows(
    rows: list[dict],
    repos: list[Repository] | None,
    repo_name: str | None,
    tool_name: str,
) -> list[dict]:
    """Apply path normalization and test-dir filtering to code-domain rows.

    Returns the filtered list. Rows with unresolvable paths are dropped and
    logged. Rows in test directories are dropped and logged.
    """
    if not repos:
        return rows
    repo_test_dirs: dict[str, list[str]] = {
        r.name: r.test_dirs for r in repos if r.test_dirs
    }
    filtered: list[dict] = []
    for row in rows:
        file_path: str = row.get("file_path", "") or ""
        result_path = normalize_file_path(file_path, repos, repo_name=repo_name)
        if result_path is None:
            logger.error(
                "Excluding row with missing file path: tool=%s rule_id=%s",
                tool_name,
                row.get("rule_id", ""),
            )
            continue
        rel, matched_repo = result_path
        row["file_path"] = rel
        if matched_repo is not None:
            row["repo"] = matched_repo
        if matched_repo is not None and rel:
            _tdirs = repo_test_dirs.get(matched_repo, [])
            if _tdirs and is_test_path(rel, _tdirs):
                logger.debug(
                    "Excluding test-dir row: tool=%s path=%s",
                    tool_name,
                    rel,
                )
                continue
        filtered.append(row)
    return filtered

"""ToolHandler protocol and path normalization helpers."""

import importlib
import inspect
import logging
from typing import Protocol

from core.config.schemas import Repository, build_excluded_dirs
from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

logger = logging.getLogger(__name__)


# ToolHandler Protocol


class ToolHandler(Protocol):
    tool_name: str
    domain: str
    segment: str
    non_enriched_fields: frozenset[str]
    normalized_fields: list[str]
    type_flags: dict[str, set[str]]
    should_enrich: bool
    should_visualize: bool
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] | None

    def normalize(self, result: ToolResult, profile: str) -> list[dict]: ...

    def render(self, row: dict) -> str: ...

    def fingerprint_key(self, finding: dict) -> str: ...


# ToolHandlerFactory


class ToolHandlerFactory:
    @staticmethod
    def load(tool_name: str) -> ToolHandler | None:
        """Load and instantiate the tool handler for tool_name, or None."""
        stem = tool_name.replace("-", "_")
        try:
            module = importlib.import_module(f"infrastructure.tools.parsers.{stem}")
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


def get_tool_domain(tool_name: str) -> str | None:
    """Return the domain ('code', 'web', 'network') for a tool, or None."""
    handler = ToolHandlerFactory.load(tool_name)
    return handler.domain if handler is not None else None


def is_excluded_path(rel_path: str, excluded_dirs: list[str]) -> bool:
    """Return True if rel_path contains any segment matching an excluded dir name.

    rel_path must start with '/': e.g. '/src/module/tests/foo.py'.
    excluded_dirs are bare dir names matched case-insensitively at any depth:
    e.g. ['tests', 'vendor'] excludes any path segment equal to those names.
    """
    parts = {p.lower() for p in rel_path.strip("/").split("/")}
    lowered = {d.lower() for d in excluded_dirs}
    return bool(parts & lowered)


def _normalize_path(file_path: str, repos: list[Repository]) -> tuple[str, int | None]:
    """Return ``(relative_path, repo_id)`` for ``file_path``.

    Identifies repos by integer ``id`` (FK to the ``repositories`` table)
    instead of mutable string name. Display sites JOIN to ``repositories``
    via ``_repo_label.label_for`` at render time.

    If ``file_path`` starts with ``repo.path``, strip that prefix.
    If no repo matches, return ``(file_path, None)`` unchanged.
    ``repo_id`` is ``None`` when no match is found, when the matched
    repo has no DB id (legacy/unsynced), or when ``file_path`` is
    empty.
    """
    if not file_path:
        return (file_path, None)
    for repo in repos:
        if repo.path and file_path.startswith(repo.path):
            rel = "/" + file_path[len(repo.path) :].lstrip("/")
            rid = getattr(repo, "id", None)
            return (rel, rid if isinstance(rid, int) else None)
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
) -> tuple[str, int | None] | None:
    """Normalize ``file_path`` relative to ``repositories``.

    Returns ``(relative_path, repo_id)`` or ``None`` when ``file_path``
    is empty. When ``repo_name`` is provided, strips that repo's path
    prefix and returns its DB ``id``; otherwise finds the best-matching
    repo from the list. ``repo_id`` may be ``None`` when no repo
    matches or when the matched repo lacks a DB id (legacy/unsynced).
    """
    if not file_path:
        return None
    if repo_name is not None:
        rel = _relativize_path(file_path, repo_name, repositories)
        rid: int | None = None
        for r in repositories:
            if r.name == repo_name:
                cand = getattr(r, "id", None)
                if isinstance(cand, int):
                    rid = cand
                break
        return (rel, rid)
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

    Each surviving row is annotated with ``repo_id`` (int) when the
    matched repo carries a DB id, and with ``repo`` (string name) for
    legacy display consumers (reporting / draft generation) that
    haven't been migrated to the JOIN-on-render model yet.
    """
    if not repos:
        return rows
    repo_excluded_dirs: dict[int, list[str]] = {}
    repo_name_by_id: dict[int, str] = {}
    for r in repos:
        rid = r.id
        if not isinstance(rid, int):
            continue
        excl = build_excluded_dirs(r)
        if excl:
            repo_excluded_dirs[rid] = excl
        if r.name:
            repo_name_by_id[rid] = r.name
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
        rel, matched_repo_id = result_path
        row["file_path"] = rel
        if matched_repo_id is not None:
            row["repo_id"] = matched_repo_id
            display_name = repo_name_by_id.get(matched_repo_id)
            if display_name:
                row["repo"] = display_name
        if matched_repo_id is not None and rel:
            _excl = repo_excluded_dirs.get(matched_repo_id, [])
            if _excl and is_excluded_path(rel, _excl):
                logger.debug(
                    "Excluding dir row: tool=%s path=%s",
                    tool_name,
                    rel,
                )
                continue
        filtered.append(row)
    return filtered

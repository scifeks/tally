"""Unified REPL search command parser (Factory + Strategy)."""

from __future__ import annotations

from typing import Any, Protocol

from core.tools.constants import DOMAINS, FINDING_TYPES, SEVERITY_LEVELS

_DEFAULT_PAGE_SIZE = 200


class SearchValidationError(Exception):
    """User-facing validation error for search query parsing."""


# ---------------------------------------------------------------------------
# SQLite strategy helpers (verbatim from sqlite_store.py)
# ---------------------------------------------------------------------------

# Flag name → SQLite column name
_FLAG_TO_COLUMN: dict[str, str] = {
    "tool": "tool",
    "domain": "domain",
    "type": "finding_type",
    "severity": "severity",
    "confidence": "confidence",
    "file": "file",
    "rule": "rule_id",
    "url": "url",
    "host": "host",
    "port": "port",
    "vulnerability_id": "vulnerability_id",
    "package_name": "package_name",
    "ecosystem": "ecosystem",
}

# Meta flags and their actual JSON path field names
_META_FLAG_FIELDS: dict[str, str] = {
    "risk_type": "risk_type",
    "profile": "profile",
    "param": "param",
    "alert": "alert_name",
    "method": "method",
    "service": "service",
    "transport": "transport",
}


def _resolve_col_expr(flag: str) -> str:
    """Return the SQLite column expression for a flag name."""
    if flag in _META_FLAG_FIELDS:
        field = _META_FLAG_FIELDS[flag]
        return f"json_extract(meta, '$.{field}')"
    if flag in _FLAG_TO_COLUMN:
        return _FLAG_TO_COLUMN[flag]
    raise SearchValidationError(
        f"Unknown filter flag '--{flag}'. Run 'search --help' for valid flags."
    )


def _validate_flag_values(
    flag: str, values: list[str], known_tools: frozenset[str]
) -> None:
    """Validate controlled-vocabulary flags. Raises SearchValidationError."""
    if flag == "tool":
        for v in values:
            if v not in known_tools:
                raise SearchValidationError(
                    f"Tool {v!r} not found. Run 'tools' to see configured tools."
                )
    elif flag == "domain":
        for v in values:
            if v not in DOMAINS:
                raise SearchValidationError(
                    f"Unknown domain {v!r}. Valid domains: {', '.join(sorted(DOMAINS))}"
                )
    elif flag == "type":
        for v in values:
            if v not in FINDING_TYPES:
                raise SearchValidationError(
                    f"Unknown type {v!r}. "
                    f"Valid types: {', '.join(sorted(FINDING_TYPES))}"
                )
    elif flag == "severity":
        for v in values:
            if v not in SEVERITY_LEVELS:
                raise SearchValidationError(
                    f"Unknown severity {v!r}. "
                    f"Valid severities: {', '.join(sorted(SEVERITY_LEVELS))}"
                )


# ---------------------------------------------------------------------------
# Strategy Protocol
# ---------------------------------------------------------------------------


class _SearchStrategy(Protocol):
    def handle_flag(
        self,
        flag: str,
        val: str,
        contains: bool,
        known_tools: frozenset[str],
    ) -> None: ...

    def build_result(self, page: int, page_size: int) -> Any: ...


# ---------------------------------------------------------------------------
# SQLite strategy
# ---------------------------------------------------------------------------


class _SqliteStrategy:
    def __init__(self) -> None:
        self._conditions: list[tuple[str, str, list[str]]] = []
        self._fields: list[str] = []

    def handle_flag(
        self,
        flag: str,
        val: str,
        contains: bool,
        known_tools: frozenset[str],
    ) -> None:
        if flag == "fields":
            parsed = [f.strip() for f in val.split(",") if f.strip()]
            if not parsed:
                raise SearchValidationError(
                    "--fields requires at least one field name, "
                    "e.g. --fields=severity,file_path"
                )
            self._fields = parsed
            return
        col_expr = _resolve_col_expr(flag)
        values = [v.strip() for v in val.split(",") if v.strip()]
        if contains:
            if values:
                self._conditions.append((col_expr, "~=", values))
        else:
            _validate_flag_values(flag, values, known_tools)
            if values:
                self._conditions.append((col_expr, "=", values))

    def build_result(self, page: int, page_size: int) -> dict[str, Any]:
        return {
            "conditions": self._conditions,
            "page": page,
            "page_size": page_size,
            "fields": self._fields,
        }


# ---------------------------------------------------------------------------
# Chroma strategy
# ---------------------------------------------------------------------------


class _ChromaDBStrategy:
    def __init__(self) -> None:
        self._filter_clauses: list[dict] = []

    def handle_flag(
        self,
        flag: str,
        val: str,
        contains: bool,
        known_tools: frozenset[str],
    ) -> None:
        from core.rag.search_parser import _handle_search_flag  # lazy: avoids cycle

        _handle_search_flag(
            flag,
            val,
            contains=contains,
            filter_clauses=self._filter_clauses,
            known_tools=known_tools,
        )

    def build_result(self, page: int, page_size: int) -> Any:
        from core.rag.search_parser import (  # lazy: avoids cycle
            SearchQuery,
            _combine_clauses,
        )

        where_filter = _combine_clauses(self._filter_clauses)
        return SearchQuery(
            semantic_text=None,
            where_filter=where_filter,
            is_semantic=False,
            page_size=page_size,
            page=page,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class SearchParserFactory:
    _REGISTRY: dict[str, type] = {
        "sqlite": _SqliteStrategy,
        "chromadb": _ChromaDBStrategy,
    }

    def create(self, backend: str) -> _SearchStrategy:
        cls = self._REGISTRY.get(backend)
        if cls is None:
            raise ValueError(f"Unknown search backend: {backend!r}")
        return cls()  # type: ignore[return-value]


_factory = SearchParserFactory()


# ---------------------------------------------------------------------------
# Shared token-processing loop
# ---------------------------------------------------------------------------


def _parse_with_strategy(
    args: list[str],
    strategy: _SearchStrategy,
    known_tools: frozenset[str],
    default_page_size: int = _DEFAULT_PAGE_SIZE,
) -> Any:
    """Process --flag=value args, delegating flag handling to *strategy*."""
    page_size: int | None = None
    page: int = 1

    for arg in args:
        if not arg.startswith("--"):
            if "~=" in arg or "=" in arg:
                raise SearchValidationError(
                    f"Old syntax detected: '{arg}'\n"
                    "Use --flag=value syntax. "
                    "Run 'search --help' for examples."
                )
            raise SearchValidationError(
                f"Unexpected argument: '{arg}'\n"
                "All search arguments use --flag=value syntax. "
                "Run 'search --help' for examples."
            )

        rest = arg[2:]  # strip "--"

        if "~=" in rest:
            key, _, value = rest.partition("~=")
            strategy.handle_flag(key, value, contains=True, known_tools=known_tools)
            continue

        if "=" not in rest:
            raise SearchValidationError(
                f"Flag '{arg}' requires a value, e.g. {arg}=<value>."
            )

        flag, _, val = rest.partition("=")

        if flag == "page-size":
            try:
                page_size = int(val)
                if page_size < 1:
                    raise ValueError
            except ValueError:
                raise SearchValidationError("--page-size must be a positive integer.")
        elif flag == "page":
            try:
                page = int(val)
                if page < 1:
                    raise ValueError
            except ValueError:
                raise SearchValidationError("--page must be a positive integer.")
        elif flag == "help":
            pass  # handled upstream in cmd_search
        else:
            strategy.handle_flag(flag, val, contains=False, known_tools=known_tools)

    if page_size is None:
        page_size = default_page_size

    return strategy.build_result(page, page_size)


# ---------------------------------------------------------------------------
# Public facades
# ---------------------------------------------------------------------------


def parse_sqlite_search_command(
    args: list[str],
    known_tools: frozenset[str],
) -> dict[str, Any]:
    """Parse --flag=value search args into a structured filter dict for SQLite."""
    strategy = _factory.create("sqlite")
    result: dict[str, Any] = _parse_with_strategy(args, strategy, known_tools)
    return result


def parse_chromadb_search_command(
    args: list[str],
    known_tools: frozenset[str],
) -> Any:
    """Parse --flag=value search args into a SearchQuery for ChromaDB."""
    strategy = _factory.create("chromadb")
    return _parse_with_strategy(args, strategy, known_tools)

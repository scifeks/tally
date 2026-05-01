"""Structured filter + semantic search query parser for tally search command."""

from __future__ import annotations

from dataclasses import dataclass

from application.ports.filters import And, Contains, Eq, Filter
from application.rag.ingestor import get_tool_domain
from core.exceptions import SearchValidationError
from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    DOMAINS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
)

_DEFAULT_SEMANTIC_PAGE_SIZE = 20
_DEFAULT_METADATA_PAGE_SIZE = 200

# Maps user-facing filter key → (metadata_field, always_contains).
# always_contains=True: emit Contains regardless of = vs ~=.
# always_contains=False: respect user's operator.
_KEY_MAP: dict[str, tuple[str, bool]] = {
    # Global
    "tool": ("tool", False),
    "domain": ("domain", False),
    # "type" is handled specially — not in this dict
    "severity": ("severity", False),
    "confidence": ("confidence", False),
    "risk_type": ("risk_type", False),
    "profile": ("profile", False),
    # Code domain
    "file": ("file_path", True),
    "rule": ("rule_id", False),
    # Web domain
    "url": ("url", True),
    "method": ("method", False),  # uppercased before querying
    "param": ("param", True),
    "alert": ("alert_name", True),
    # Network domain
    "host": ("ip_address", False),
    "port": ("port", False),  # int conversion required
    "service": ("service", True),
    "transport": ("transport", False),
}

_VALID_KEYS: frozenset[str] = frozenset(_KEY_MAP) | {"type"}

_DOMAIN_KEYS: dict[str, list[str]] = {
    "code": ["file", "rule"],
    "web": ["url", "method", "param", "alert"],
}


@dataclass
class SearchQuery:
    semantic_text: str | None  # free text for embedding search
    where_filter: Filter | None  # storage-agnostic filter (None = no filter)
    is_semantic: bool  # True iff semantic_text is non-empty
    page_size: int  # results per page
    page: int  # 1-indexed page number (default 1)


def _resolve_type_filter(value: str) -> Filter:
    types = [t.strip() for t in value.split(",")]
    for t in types:
        if t not in FINDING_TYPES:
            raise SearchValidationError(
                f"Unknown type {t!r}. Valid types: {', '.join(sorted(FINDING_TYPES))}"
            )
    if len(types) == 1:
        return Eq(f"type_{types[0]}", True)
    return And(clauses=tuple(Eq(f"type_{t}", True) for t in types))


def _add_filter(
    key: str,
    value: str,
    contains: bool,
    filter_clauses: list[Filter],
    known_tools: frozenset[str],
    active_tool: str | None = None,
) -> None:
    if key not in _VALID_KEYS:
        if active_tool is not None:
            domain = get_tool_domain(active_tool)
            if domain:
                keys_str = ", ".join(_DOMAIN_KEYS.get(domain, []))
                raise SearchValidationError(
                    f"Unknown filter key {key!r}.\n"
                    f"Valid keys for {active_tool}: {keys_str} (plus global keys).\n"
                    f"Run 'help search {active_tool}' for full reference."
                )
        raise SearchValidationError(
            f"Unknown filter key {key!r}.\n"
            "Run 'help search' for valid filter keys and examples."
        )
    if key == "type":
        filter_clauses.append(_resolve_type_filter(value))
        return

    field, always_contains = _KEY_MAP[key]
    use_contains = contains or always_contains

    # Value validation for controlled vocabularies
    if key == "tool" and value not in known_tools:
        raise SearchValidationError(
            f"Tool {value!r} not found. Run 'tools' to see configured tools."
        )
    if key == "severity" and value not in SEVERITY_LEVELS:
        raise SearchValidationError(
            f"Unknown severity {value!r}. "
            f"Valid severities: {', '.join(sorted(SEVERITY_LEVELS))}"
        )
    if key == "confidence" and value not in CONFIDENCE_LEVELS:
        raise SearchValidationError(
            f"Unknown confidence {value!r}. "
            f"Valid confidence levels: {', '.join(sorted(CONFIDENCE_LEVELS))}"
        )
    if key == "domain" and value not in DOMAINS:
        raise SearchValidationError(
            f"Unknown domain {value!r}. Valid domains: {', '.join(sorted(DOMAINS))}"
        )

    # Type coercions
    if key == "method":
        value = value.upper()
    if key == "port":
        try:
            int_val: int = int(value)
        except ValueError:
            raise SearchValidationError("Port must be a number.")
        filter_clauses.append(Eq(field, int_val))
        return

    if use_contains:
        filter_clauses.append(Contains(field, value))
    else:
        filter_clauses.append(Eq(field, value))


def handle_search_flag(
    key: str,
    value: str,
    contains: bool,
    filter_clauses: list[Filter],
    known_tools: frozenset[str],
) -> None:
    """Handle a single --flag=value token from parse_search_command."""
    if key == "type":
        filter_clauses.append(_resolve_type_filter(value))
    elif key == "tool":
        tools = [t.strip() for t in value.split(",")]
        for t in tools:
            if t not in known_tools:
                raise SearchValidationError(
                    f"Tool {t!r} not found. Run 'tools' to see configured tools."
                )
        if len(tools) == 1:
            filter_clauses.append(Eq("tool", tools[0]))
        else:
            filter_clauses.append(And(clauses=tuple(Eq("tool", t) for t in tools)))
    elif key == "severity":
        severities = [s.strip() for s in value.split(",")]
        for s in severities:
            if s not in SEVERITY_LEVELS:
                raise SearchValidationError(
                    f"Unknown severity {s!r}. "
                    f"Valid severities: {', '.join(sorted(SEVERITY_LEVELS))}"
                )
        if len(severities) == 1:
            filter_clauses.append(Eq("severity", severities[0]))
        else:
            filter_clauses.append(
                And(clauses=tuple(Eq("severity", s) for s in severities))
            )
    elif key in _KEY_MAP:
        _add_filter(key, value, contains, filter_clauses, known_tools)
    else:
        if contains:
            filter_clauses.append(Contains(key, value))
        else:
            filter_clauses.append(Eq(key, value))


def combine_clauses(clauses: list[Filter]) -> Filter | None:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return And(clauses=tuple(clauses))


def parse_search_query(
    raw: str,
    known_tools: frozenset[str],
) -> SearchQuery:
    """Parse a raw search string into a SearchQuery.

    Tokens are whitespace-split and classified as:
    - Pagination flags: --page-size=N, --page=N
    - Contains filter: key~=value
    - Exact filter: key=value
    - Bare token: implicit tool match or semantic text
    """
    semantic_parts: list[str] = []
    filter_clauses: list[Filter] = []
    page_size: int | None = None
    page: int = 1

    # Pre-scan for active tool so _add_filter can produce contextual errors.
    active_tool: str | None = None
    for token in raw.split():
        if token.startswith("tool=") and not token.startswith("--"):
            candidate = token[5:]
            if candidate in known_tools:
                active_tool = candidate
            break

    for token in raw.split():
        if token.startswith("--"):
            if "=" not in token:
                raise SearchValidationError(
                    f"Flag {token!r} requires a value, e.g. {token}=<n>."
                )
            flag, _, val = token[2:].partition("=")
            if flag == "page-size":
                try:
                    page_size = int(val)
                    if page_size < 1:
                        raise ValueError
                except ValueError:
                    raise SearchValidationError(
                        "--page-size must be a positive integer."
                    )
            elif flag == "page":
                try:
                    page = int(val)
                    if page < 1:
                        raise ValueError
                except ValueError:
                    raise SearchValidationError("--page must be a positive integer.")
            else:
                raise SearchValidationError(
                    f"Unknown flag '--{flag}'. Supported flags: --page-size, --page."
                )
        elif "~=" in token:
            key, _, value = token.partition("~=")
            _add_filter(
                key,
                value,
                contains=True,
                filter_clauses=filter_clauses,
                known_tools=known_tools,
                active_tool=active_tool,
            )
        elif "=" in token:
            key, _, value = token.partition("=")
            _add_filter(
                key,
                value,
                contains=False,
                filter_clauses=filter_clauses,
                known_tools=known_tools,
                active_tool=active_tool,
            )
        else:
            clean = token.lower().rstrip("?.,!:;")
            if clean in known_tools:
                filter_clauses.append(Eq("tool", clean))
            else:
                semantic_parts.append(token)

    semantic_text = " ".join(semantic_parts).strip() or None
    where_filter = combine_clauses(filter_clauses)
    is_semantic = semantic_text is not None

    if page_size is None:
        page_size = (
            _DEFAULT_SEMANTIC_PAGE_SIZE if is_semantic else _DEFAULT_METADATA_PAGE_SIZE
        )

    return SearchQuery(
        semantic_text=semantic_text,
        where_filter=where_filter,
        is_semantic=is_semantic,
        page_size=page_size,
        page=page,
    )

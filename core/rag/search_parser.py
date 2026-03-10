"""Structured filter + semantic search query parser for tally search command."""

from __future__ import annotations

from dataclasses import dataclass

from core.tools.constants import (
    CONFIDENCE_LEVELS,
    DOMAINS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
    TOOL_DOMAIN_MAP,
)

_DEFAULT_SEMANTIC_PAGE_SIZE = 20
_DEFAULT_METADATA_PAGE_SIZE = 200

# Maps user-facing filter key → (metadata_field, always_contains).
# always_contains=True: use $contains regardless of = vs ~=.
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
    "network": ["host", "port", "service", "transport"],
}


class SearchValidationError(Exception):
    """User-facing validation error for search query parsing."""


@dataclass
class SearchQuery:
    semantic_text: str | None  # free text for embedding search
    where_filter: dict | None  # ChromaDB where clause (None = no filter)
    is_semantic: bool  # True iff semantic_text is non-empty
    page_size: int  # results per page
    page: int  # 1-indexed page number (default 1)


def _resolve_type_filter(value: str) -> dict:
    types = [t.strip() for t in value.split(",")]
    for t in types:
        if t not in FINDING_TYPES:
            raise SearchValidationError(
                f"Unknown type {t!r}. Valid types: {', '.join(sorted(FINDING_TYPES))}"
            )
    if len(types) == 1:
        return {f"type_{types[0]}": {"$eq": True}}
    return {"$and": [{f"type_{t}": {"$eq": True}} for t in types]}


def _add_filter(
    key: str,
    value: str,
    contains: bool,
    filter_clauses: list[dict],
    known_tools: frozenset[str],
    active_tool: str | None = None,
) -> None:
    if key not in _VALID_KEYS:
        if active_tool is not None:
            domain = TOOL_DOMAIN_MAP.get(active_tool)
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
        filter_clauses.append({field: {"$eq": int_val}})
        return

    op = "$contains" if use_contains else "$eq"
    filter_clauses.append({field: {op: value}})


def _combine_clauses(clauses: list[dict]) -> dict | None:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


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
    filter_clauses: list[dict] = []
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
                filter_clauses.append({"tool": {"$eq": clean}})
            else:
                semantic_parts.append(token)

    semantic_text = " ".join(semantic_parts).strip() or None
    where_filter = _combine_clauses(filter_clauses)
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

"""Table rendering logic extracted from knowledge_commands."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from rich.table import Table

from domain.tools.constants import BOOLEAN_TYPE_FIELDS

if TYPE_CHECKING:
    from application.tools.registry import ToolRegistry

# Shared utilities

_SEVERITY_COLORS = {
    "critical": "red",
    "high": "orange1",
    "medium": "yellow",
    "low": "blue",
    "informational": "white",
}


def _extract_types(meta: dict) -> str:
    """Return comma-separated list of active type_* fields."""
    active = [
        field[5:]  # strip "type_" prefix
        for field in sorted(BOOLEAN_TYPE_FIELDS)
        if meta.get(field)
    ]
    return ", ".join(active)


def render_finding_type(meta: dict) -> str:
    """Render finding_type for display: join list, fall back to type_* booleans."""
    ft = meta.get("finding_type")
    if isinstance(ft, list):
        return ", ".join(ft)
    if isinstance(ft, str) and ft:
        return ft
    return _extract_types(meta)


def color_severity(sev: str) -> str:
    color = _SEVERITY_COLORS.get(sev, "white")
    return f"[{color}]{sev}[/{color}]" if sev else ""


# Schema constants

_ALL_NORMALIZED_FIELDS: list[str] = [
    "confidence",
    "cwe",
    "description",
    "domain",
    "ecosystem",
    "file_path",
    "finding_type",
    "ip_address",
    "package_name",
    "package_version",
    "port",
    "rule_id",
    "severity",
    "tool",
    "url",
    "vulnerability_id",
]

_SQLITE_SCHEMA_FIELDS: frozenset[str] = frozenset(
    {
        "fingerprint",
        "run_id",
        "tool",
        "domain",
        "finding_type",
        "severity",
        "confidence",
        "file",
        "file_path",
        "rule_id",
        "url",
        "host",
        "ip_address",
        "port",
        "vulnerability_id",
        "package_name",
        "ecosystem",
        "description",
        "package_version",
        "cwe",
        "enriched",
    }
)


# TableRenderer Protocol


@runtime_checkable
class TableRenderer(Protocol):
    tool_name: str
    normalized_fields: list[str]

    def build(self, results: list[dict[str, Any]], is_semantic: bool) -> Table: ...


# Table builder functions (generic / fields)


def _build_fields_table(results: list[dict[str, Any]], fields: list[str]) -> Table:
    """Build a custom projection table using user-specified field names."""
    table = Table(show_header=True, header_style="bold")
    for f in fields:
        table.add_column(f, overflow="fold")
    for r in results:
        meta = r["metadata"]
        row: list[str] = []
        for f in fields:
            val = meta.get(f)
            if val is None or val == "":
                row.append("N/A")
            elif f == "severity":
                row.append(color_severity(str(val)))
            elif isinstance(val, list):
                row.append(", ".join(str(v) for v in val))
            else:
                row.append(str(val))
        table.add_row(*row)
    return table


def _truncate(text: str, max_len: int = 65) -> str:
    """Truncate text to max_len characters, appending … if cut."""
    if not text or len(text) <= max_len:
        return text or ""
    return text[: max_len - 1] + "…"


def _build_generic_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build the default findings table: Severity | Type | Description | Tool."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Severity", no_wrap=True)
    table.add_column("Type", style="green", no_wrap=True)
    table.add_column("Description", overflow="fold")
    table.add_column("Tool", style="cyan", no_wrap=True)
    if is_semantic:
        table.add_column("Relevance", style="dim", no_wrap=True)

    for r in results:
        meta = r["metadata"]
        sev = meta.get("severity", "")
        row: list[str] = [
            color_severity(sev),
            render_finding_type(meta),
            _truncate(meta.get("description", "")),
            meta.get("tool", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


# Factory


class FindingsTableFactory:
    """Factory that discovers and delegates to tool-specific table renderers."""

    def __init__(self, *, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
        self._renderers: dict[str, TableRenderer] = {}
        self._load_renderers()

    def _load_renderers(self) -> None:
        for tool_name in self._tool_registry.list_tool_names():
            file_stem = tool_name.replace("-", "_")
            try:
                mod = importlib.import_module(
                    f"application.repl.commands.renderers.{file_stem}"
                )
                r = getattr(mod, "renderer", None)
                if isinstance(r, TableRenderer):
                    self._renderers[tool_name] = r
            except ImportError:
                pass  # no renderer for this tool → falls through to generic

    def build(
        self,
        results: list[dict[str, Any]],
        is_semantic: bool,
        tool_filter: str | None = None,
    ) -> Table:
        """Return a tool-specific table when tool_filter is set, else generic.

        Tool-specific renderers are only invoked for ``search --tool=<name>``
        without ``--fields``. All other queries use the generic default view.
        """
        if tool_filter is not None:
            renderer = self._renderers.get(tool_filter)
            if renderer is not None:
                return renderer.build(results, is_semantic)
        return _build_generic_table(results, is_semantic)

    def build_fields(self, results: list[dict[str, Any]], fields: list[str]) -> Table:
        """Return a custom projection table for the given fields."""
        return _build_fields_table(results, fields)

    def discover_tool_fields(
        self, sqlite_store: Any, tool_name: str
    ) -> tuple[list[str], list[str]] | None:
        """Return (schema_fields, meta_fields) for tool_name, or None if no rows."""
        from application.rag.ingestor import ToolHandlerFactory

        count, meta_keys = sqlite_store.get_tool_meta_keys(tool_name)
        if count == 0:
            return None
        handler = ToolHandlerFactory.load(tool_name)
        normalized = set(
            handler.normalized_fields if handler is not None else _ALL_NORMALIZED_FIELDS
        )
        schema = sorted(normalized | {"fingerprint", "run_id"})
        meta = sorted(meta_keys - _SQLITE_SCHEMA_FIELDS)
        return schema, meta

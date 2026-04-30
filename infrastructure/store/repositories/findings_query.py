"""SQL query builder for findings searches.

``FindingQueryBuilder`` constructs the SELECT + WHERE + ORDER BY + LIMIT/OFFSET
SQL from a structured ``filters`` dict.  No DB connection is used here.
"""

from __future__ import annotations

from typing import Any

from domain.findings.severity import Severity
from domain.findings.sort import FindingSortColumn, SortDirection


class FindingQueryBuilder:
    """Build a parameterised SQL query from a structured filters dict.

    ``filters`` format::

        {
            "conditions": [(col_expr, op, values), ...],
            "sort_by":    FindingSortColumn | None,
            "sort_dir":   SortDirection | None,
            "page":       1,
            "page_size":  200,
            "offset":     int | None,
            "limit":      int | None,
            "search":     str | None,
        }

    When ``offset`` and ``limit`` are both present they take precedence over
    ``page`` / ``page_size`` for pagination.  ``search`` performs a
    substring match across ``description``, ``url``, and ``file``.
    """

    _BASE_SELECT = """
        SELECT id, fingerprint, run_id,
               tool, domain, segment, repo_id,
               finding_type, severity, confidence,
               file, rule_id, url,
               vulnerability_id, package_name, ecosystem,
               description, package_version, cwe, enriched, meta,
               first_seen, last_seen, status
        FROM findings
    """

    def __init__(self, filters: dict[str, Any]) -> None:
        self._conditions: list[tuple[str, str, list[str]]] = filters.get(
            "conditions", []
        )
        self._sort_by: FindingSortColumn | None = filters.get("sort_by")
        self._sort_dir: SortDirection | None = filters.get("sort_dir")
        self._page: int = filters.get("page", 1)
        self._page_size: int = filters.get("page_size", 200)
        self._offset: int | None = filters.get("offset")
        self._limit: int | None = filters.get("limit")
        self._search: str | None = filters.get("search")

    def build_where_parts(self) -> tuple[list[str], list[Any]]:
        """Return (where_parts, params) for callers composing custom SQL.

        Public counterpart of :py:meth:`_build_where`. Used by repository
        methods (e.g. ``filter_options``) that need to share the exact
        filter semantics with ``search_raw`` while running their own
        SELECT/GROUP BY shapes.
        """
        return self._build_where()

    def _build_where(self) -> tuple[list[str], list[Any]]:
        """Return (where_parts, params) without ORDER BY / LIMIT."""
        where_parts: list[str] = []
        params: list[Any] = []

        for col_expr, op, values in self._conditions:
            if not values:
                continue
            if col_expr == "finding_type":
                # finding_type is stored as a JSON array; use json_each().
                if op == "=":
                    # OR semantics: row matches if any element equals any value.
                    if len(values) == 1:
                        where_parts.append(
                            "EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                            " WHERE json_each.value = ?)"
                        )
                        params.append(values[0])
                    else:
                        phs = ",".join("?" * len(values))
                        where_parts.append(
                            "EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                            f" WHERE json_each.value IN ({phs}))"
                        )
                        params.extend(values)
                elif op == "~=":
                    like_clauses = " OR ".join("json_each.value LIKE ?" for _ in values)
                    where_parts.append(
                        "EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                        f" WHERE {like_clauses})"
                    )
                    params.extend(f"%{v}%" for v in values)
            elif col_expr == "severity":
                # Translate string label(s) to integer ranks for storage.
                if op == "=":
                    int_values = [Severity.from_label(v).rank for v in values]
                    if len(int_values) == 1:
                        where_parts.append("severity = ?")
                        params.append(int_values[0])
                    else:
                        placeholders = ",".join("?" * len(int_values))
                        where_parts.append(f"severity IN ({placeholders})")
                        params.extend(int_values)
                elif op == "~=":
                    # LIKE on severity doesn't make sense semantically; treat
                    # as exact match after label translation.
                    int_values = [Severity.from_label(v).rank for v in values]
                    if len(int_values) == 1:
                        where_parts.append("severity = ?")
                        params.append(int_values[0])
                    else:
                        placeholders = ",".join("?" * len(int_values))
                        where_parts.append(f"severity IN ({placeholders})")
                        params.extend(int_values)
            elif op == "=":
                if len(values) == 1:
                    where_parts.append(f"{col_expr} = ?")
                    params.append(values[0])
                else:
                    placeholders = ",".join("?" * len(values))
                    where_parts.append(f"{col_expr} IN ({placeholders})")
                    params.extend(values)
            elif op == "~=":
                like_parts = [f"{col_expr} LIKE ?"] * len(values)
                where_parts.append(f"({'  OR  '.join(like_parts)})")
                params.extend(f"%{v}%" for v in values)

        if self._search:
            term = f"%{self._search}%"
            where_parts.append(
                "(json_extract(meta, '$.title') LIKE ?"
                " OR tool LIKE ? OR description LIKE ?"
                " OR url LIKE ? OR file LIKE ? OR cwe LIKE ?)"
            )
            params.extend([term] * 6)

        return where_parts, params

    def build(self) -> tuple[str, list[Any]]:
        """Return ``(sql, params)`` ready for ``conn.execute``."""
        where_parts, params = self._build_where()

        sql = self._BASE_SELECT
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        sort_col = self._sort_by or FindingSortColumn.FIRST_SEEN
        sort_dir = self._sort_dir or SortDirection.DESC
        sql += f" ORDER BY {sort_col.sql_expr} {sort_dir.value}, id {sort_dir.value}"

        if self._offset is not None and self._limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([self._limit, self._offset])
        else:
            offset = (self._page - 1) * self._page_size
            sql += " LIMIT ? OFFSET ?"
            params.extend([self._page_size, offset])

        return sql, params

    def build_count(self) -> tuple[str, list[Any]]:
        """Return ``(sql, params)`` for a COUNT(*) query with the same filters."""
        where_parts, params = self._build_where()
        sql = "SELECT COUNT(*) FROM findings"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        return sql, params

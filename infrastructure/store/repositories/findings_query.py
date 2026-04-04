"""SQL query builder for findings searches.

``FindingQueryBuilder`` constructs the SELECT + WHERE + LIMIT/OFFSET SQL
from a structured ``filters`` dict.  No DB connection is used here.
"""

from __future__ import annotations

from typing import Any


class FindingQueryBuilder:
    """Build a parameterised SQL query from a structured filters dict.

    ``filters`` format::

        {
            "conditions": [(col_expr, op, values), ...],
            "page": 1,
            "page_size": 200,
        }
    """

    _BASE_SELECT = """
        SELECT fingerprint, run_id,
               tool, domain, segment, repo,
               finding_type, severity, confidence,
               file, rule_id, url,
               vulnerability_id, package_name, ecosystem,
               description, package_version, cwe, enriched, meta
        FROM findings
    """

    def __init__(self, filters: dict[str, Any]) -> None:
        self._conditions: list[tuple[str, str, list[str]]] = filters.get(
            "conditions", []
        )
        self._page: int = filters.get("page", 1)
        self._page_size: int = filters.get("page_size", 200)

    def build(self) -> tuple[str, list[Any]]:
        """Return ``(sql, params)`` ready for ``conn.execute``."""
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
                            f"EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                            f" WHERE json_each.value IN ({phs}))"
                        )
                        params.extend(values)
                elif op == "~=":
                    like_clauses = " OR ".join("json_each.value LIKE ?" for _ in values)
                    where_parts.append(
                        f"EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                        f" WHERE {like_clauses})"
                    )
                    params.extend(f"%{v}%" for v in values)
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

        sql = self._BASE_SELECT
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        offset = (self._page - 1) * self._page_size
        sql += " LIMIT ? OFFSET ?"
        params.extend([self._page_size, offset])

        return sql, params

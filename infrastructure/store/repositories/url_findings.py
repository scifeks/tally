"""CRUD for the url_findings table.

Stores one row per discovered URL: SCAN-sourced from Katana/Noir
(linked to scan_runs) and USER-sourced from user-uploaded endpoint files.

A UNIQUE expression index enforces dedup across (repo_id, source, tool,
file_path, method, protocol, host, port, path). insert_many uses
INSERT OR IGNORE to silently absorb duplicates within a batch.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from application.ports.url_finding_repository import UrlFindingRepositoryPort
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool

if TYPE_CHECKING:
    import sqlite3

    from infrastructure.store.connection import ConnectionFactory


_SORT_COL_MAP: dict[str, str] = {
    "host": "uf.host",
    "path": "uf.path",
    "method": "uf.method",
    "port": "uf.port",
    "protocol": "uf.protocol",
    "id": "uf.id",
    "created_at": "uf.created_at",
    "repo": "r.name",
}
_VALID_ORDERS: frozenset[str] = frozenset({"asc", "desc"})


def _in_clause(
    col: str, values: list[Any], parts: list[str], params: list[Any]
) -> None:
    if not values:
        return
    if len(values) == 1:
        parts.append(f"{col} = ?")
        params.append(values[0])
    else:
        placeholders = ",".join("?" * len(values))
        parts.append(f"{col} IN ({placeholders})")
        params.extend(values)


def _build_where(
    *,
    repo_id: list[int] | None = None,
    source: UrlSource | None = None,
    tool: UrlTool | None = None,
    method: list[str] | None = None,
    protocol: list[str] | None = None,
    host: list[str] | None = None,
    port: list[int] | None = None,
    path: list[str] | None = None,
    search: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Return (where_parts, params) shared by ``list_paginated`` and
    ``filter_options``. The ``r.deleted_at IS NULL`` clause excludes
    soft-deleted repos and assumes the caller joins ``repositories AS r``.
    """
    parts: list[str] = ["r.deleted_at IS NULL"]
    params: list[Any] = []
    _in_clause("uf.repo_id", list(repo_id or []), parts, params)
    if source is not None:
        parts.append("uf.source = ?")
        params.append(str(source))
    if tool is not None:
        parts.append("uf.tool = ?")
        params.append(str(tool))
    _in_clause("uf.method", list(method or []), parts, params)
    _in_clause("uf.protocol", list(protocol or []), parts, params)
    _in_clause("uf.host", list(host or []), parts, params)
    _in_clause("uf.port", list(port or []), parts, params)
    _in_clause("uf.path", list(path or []), parts, params)
    if search:
        term = f"%{search}%"
        parts.append(
            "(uf.method LIKE ? OR uf.protocol LIKE ? OR uf.host LIKE ?"
            " OR uf.path LIKE ? OR r.name LIKE ?)"
        )
        params.extend([term] * 5)
    return parts, params


class UrlFindingRepository(UrlFindingRepositoryPort):
    """SQLite-backed implementation of ``UrlFindingRepositoryPort``."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # Writes
    def insert_many(self, findings: Iterable[UrlFinding]) -> int:
        """Insert all rows; the unique index dedupes silently. Returns count
        of rows actually inserted (excluding ignored duplicates).
        """
        rows = [
            (
                f.repo_id,
                str(f.source),
                str(f.tool) if f.tool is not None else None,
                f.run_id,
                f.method,
                f.protocol,
                f.host,
                f.port,
                f.path,
                f.file_path,
                json.dumps(f.meta),
            )
            for f in findings
        ]
        if not rows:
            return 0
        sql = (
            "INSERT OR IGNORE INTO url_findings ("
            "repo_id, source, tool, run_id, method, protocol, host, port,"
            " path, file_path, meta"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self._factory.connect() as conn:
            cur = conn.executemany(sql, rows)
            return cur.rowcount

    def delete_for_repo_and_tool(self, repo_id: int, tool: UrlTool) -> int:
        """Wipe SCAN-sourced rows for ``(repo_id, tool)``. Used before re-ingest."""
        with self._factory.connect() as conn:
            cur = conn.execute(
                "DELETE FROM url_findings"
                " WHERE repo_id = ? AND source = 'scan' AND tool = ?",
                (repo_id, str(tool)),
            )
            return cur.rowcount

    def delete_for_user_file(self, repo_id: int, file_path: str) -> int:
        """Wipe USER-sourced rows tied to a specific uploaded file."""
        with self._factory.connect() as conn:
            cur = conn.execute(
                "DELETE FROM url_findings"
                " WHERE repo_id = ? AND source = 'user' AND file_path = ?",
                (repo_id, file_path),
            )
            return cur.rowcount

    def delete_for_repo(self, repo_id: int) -> int:
        """Wipe all rows for a repo. Used by hard-delete + purge cascades."""
        with self._factory.connect() as conn:
            cur = conn.execute("DELETE FROM url_findings WHERE repo_id = ?", (repo_id,))
            return cur.rowcount

    def delete_all(self) -> int:
        """Wipe every row. Used by the project-wide ``purge`` REPL command."""
        with self._factory.connect() as conn:
            cur = conn.execute("DELETE FROM url_findings")
            return cur.rowcount

    # Reads
    def list_for_repo(
        self, repo_id: int, *, source: UrlSource | None = None
    ) -> list[UrlFinding]:
        """Return all rows for a single repo, optionally filtered by source."""
        sql = "SELECT * FROM url_findings WHERE repo_id = ?"
        params: list[object] = [repo_id]
        if source is not None:
            sql += " AND source = ?"
            params.append(str(source))
        sql += " ORDER BY id"
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def list_paginated(
        self,
        *,
        repo_id: list[int] | None = None,
        source: UrlSource | None = None,
        tool: UrlTool | None = None,
        method: list[str] | None = None,
        protocol: list[str] | None = None,
        host: list[str] | None = None,
        port: list[int] | None = None,
        path: list[str] | None = None,
        search: str | None = None,
        sort: str = "host",
        order: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[UrlFinding], int]:
        """Paginated list with multi-value filters.

        Filters all use exact-match equality (``IN`` for multi-value); the
        ``search`` param is a substring match on ``path``. Joins
        ``repositories`` so soft-deleted repos are excluded.
        """
        sort_col = _SORT_COL_MAP.get(sort, "uf.host")
        order_dir = order.upper() if order.lower() in _VALID_ORDERS else "ASC"

        where_parts, params = _build_where(
            repo_id=repo_id,
            source=source,
            tool=tool,
            method=method,
            protocol=protocol,
            host=host,
            port=port,
            path=path,
            search=search,
        )
        where = " WHERE " + " AND ".join(where_parts)
        base = f"FROM url_findings uf JOIN repositories r ON r.id = uf.repo_id{where}"

        with self._factory.connect() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()
            total = total_row[0] if total_row else 0
            rows = conn.execute(
                "SELECT uf.* "
                f"{base}"
                f" ORDER BY {sort_col} {order_dir}, uf.id {order_dir}"
                " LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [self._row_to_entity(r) for r in rows], total

    def filter_options(self, filters: dict[str, Any]) -> dict:
        """Return per-dimension counts under the given filter set.

        Strict semantics: every dimension's counts apply every active
        filter, including its own dimension's filter. Options with
        ``count == 0`` are omitted (HAVING COUNT(*) > 0). All six dimension
        keys are always present (empty list when no values match).

        ``filters`` is a dict with the same keys as ``list_paginated``
        accepts (``repo_id``, ``source``, ``tool``, ``method``,
        ``protocol``, ``host``, ``port``, ``path``, ``search``).

        ``repo`` entries carry a ``label`` (repo name) since the filter
        param is ``repo_id`` but the UI displays names. ``port`` values
        are ``int``; all other ``value``s are ``str``.
        """
        where_parts, params = _build_where(
            repo_id=filters.get("repo_id"),
            source=filters.get("source"),
            tool=filters.get("tool"),
            method=filters.get("method"),
            protocol=filters.get("protocol"),
            host=filters.get("host"),
            port=filters.get("port"),
            path=filters.get("path"),
            search=filters.get("search"),
        )
        where = " WHERE " + " AND ".join(where_parts)
        join = "FROM url_findings uf JOIN repositories r ON r.id = uf.repo_id"

        with self._factory.connect() as conn:

            def _scalar(col: str) -> list[dict[str, Any]]:
                rows = conn.execute(
                    f"SELECT uf.{col}, COUNT(*) {join}{where}"
                    f" GROUP BY uf.{col} HAVING COUNT(*) > 0"
                    f" ORDER BY uf.{col}",
                    params,
                ).fetchall()
                return [{"value": v, "count": int(c)} for v, c in rows]

            method_dim = _scalar("method")
            protocol_dim = _scalar("protocol")
            host_dim = _scalar("host")
            path_dim = _scalar("path")

            port_rows = conn.execute(
                f"SELECT uf.port, COUNT(*) {join}{where}"
                " GROUP BY uf.port HAVING COUNT(*) > 0 ORDER BY uf.port",
                params,
            ).fetchall()
            port_dim = [{"value": int(v), "count": int(c)} for v, c in port_rows]

            repo_rows = conn.execute(
                f"SELECT uf.repo_id, r.name, COUNT(*) {join}{where}"
                " GROUP BY uf.repo_id, r.name HAVING COUNT(*) > 0"
                " ORDER BY r.name",
                params,
            ).fetchall()
            repo_dim = [
                {"value": int(rid), "label": name, "count": int(c)}
                for rid, name, c in repo_rows
            ]

        return {
            "method": method_dim,
            "protocol": protocol_dim,
            "host": host_dim,
            "port": port_dim,
            "path": path_dim,
            "repo": repo_dim,
        }

    def count_active(self) -> int:
        """Count rows whose owning repository is not soft-deleted."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM url_findings uf"
                " JOIN repositories r ON r.id = uf.repo_id"
                " WHERE r.deleted_at IS NULL"
            ).fetchone()
        return int(row[0]) if row else 0

    # Helpers
    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> UrlFinding:
        try:
            meta_obj = json.loads(row["meta"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta_obj = {}
        tool_val = row["tool"]
        return UrlFinding(
            id=row["id"],
            repo_id=row["repo_id"],
            source=UrlSource(row["source"]),
            tool=UrlTool(tool_val) if tool_val else None,
            run_id=row["run_id"],
            method=row["method"],
            protocol=row["protocol"],
            host=row["host"],
            port=row["port"],
            path=row["path"],
            file_path=row["file_path"],
            meta=meta_obj,
            created_at=row["created_at"],
        )

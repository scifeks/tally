"""UrlFindingRepository — CRUD for the ``url_findings`` table (Phase 9).

Stores one row per discovered URL: SCAN-sourced rows from Katana/Noir
(linked to a ``scan_runs`` row) and USER-sourced rows from user-uploaded
endpoint files.

Dedup is enforced by the ``uniq_url_findings`` UNIQUE expression index
``(repo_id, source, COALESCE(tool, ''), COALESCE(file_path, ''),
   method, protocol, host, port, path)``.
``insert_many`` uses ``INSERT OR IGNORE`` so the unique index silently
absorbs duplicates within a single insert batch (e.g. Katana finding the
same URL twice in one run).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import TYPE_CHECKING

from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool

if TYPE_CHECKING:
    import sqlite3

    from infrastructure.store.connection import ConnectionFactory


_VALID_SORT_COLUMNS: frozenset[str] = frozenset(
    {"host", "path", "method", "port", "id", "created_at"}
)
_VALID_ORDERS: frozenset[str] = frozenset({"asc", "desc"})


class UrlFindingRepository:
    """SQLite-backed implementation of ``UrlFindingRepositoryPort``."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
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
        repo_id: int | None = None,
        source: UrlSource | None = None,
        tool: UrlTool | None = None,
        search: str | None = None,
        method: str | None = None,
        sort: str = "host",
        order: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[UrlFinding], int]:
        """Paginated list. Filters: repo_id, source, tool, search (path
        substring), method. Returns ``(rows, total)``.

        Joins ``repositories`` so soft-deleted repos are excluded.
        """
        sort_col = sort if sort in _VALID_SORT_COLUMNS else "host"
        order_dir = order.upper() if order.lower() in _VALID_ORDERS else "ASC"

        clauses: list[str] = ["r.deleted_at IS NULL"]
        params: list[object] = []
        if repo_id is not None:
            clauses.append("uf.repo_id = ?")
            params.append(repo_id)
        if source is not None:
            clauses.append("uf.source = ?")
            params.append(str(source))
        if tool is not None:
            clauses.append("uf.tool = ?")
            params.append(str(tool))
        if method:
            clauses.append("uf.method = ?")
            params.append(method)
        if search:
            clauses.append("uf.path LIKE ?")
            params.append(f"%{search}%")

        where = " WHERE " + " AND ".join(clauses)
        base = f"FROM url_findings uf JOIN repositories r ON r.id = uf.repo_id{where}"

        with self._factory.connect() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()
            total = total_row[0] if total_row else 0
            rows = conn.execute(
                "SELECT uf.* "
                f"{base}"
                f" ORDER BY uf.{sort_col} {order_dir}, uf.id {order_dir}"
                " LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [self._row_to_entity(r) for r in rows], total

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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

"""SQLite adapter for the ``tool_overrides`` table."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from application.ports.tool_overrides import (
    ToolOverrideNameConflict,
    ToolOverridesRepositoryPort,
)
from domain.tool_overrides.entry import ToolOverride

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


_COLUMNS = (
    "id, tool_name, args_mode, type, location,"
    " path, container_name, container_tool_path,"
    " scope, repo_id, service_name,"
    " created_at, updated_at"
)


class ToolOverridesRepository(ToolOverridesRepositoryPort):
    """CRUD on tool_overrides table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def list_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolOverride], int]:
        with self._factory.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM tool_overrides").fetchone()[0]
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM tool_overrides"
                " ORDER BY id ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_override(r) for r in rows], int(total)

    def get_by_tool_name(self, tool_name: str) -> ToolOverride | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM tool_overrides"
                " WHERE tool_name = ? AND scope = 'global'",
                (tool_name,),
            ).fetchone()
        return _row_to_override(row) if row else None

    def find_service_scoped(
        self,
        tool_name: str,
        repo_id: int,
        service_name: str,
    ) -> ToolOverride | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM tool_overrides"
                " WHERE tool_name = ? AND scope = 'service'"
                " AND repo_id = ? AND service_name = ?",
                (tool_name, repo_id, service_name),
            ).fetchone()
        return _row_to_override(row) if row else None

    def insert(
        self,
        *,
        tool_name: str,
        args_mode: Literal["stock", "custom"],
        type: Literal["repo", "api"],
        location: Literal["local", "docker"],
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
        scope: Literal["global", "service"] = "global",
        repo_id: int | None = None,
        service_name: str | None = None,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        try:
            with self._factory.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO tool_overrides ("
                    "tool_name, args_mode, type, location,"
                    " path, container_name, container_tool_path,"
                    " scope, repo_id, service_name,"
                    " created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tool_name,
                        args_mode,
                        type,
                        location,
                        path,
                        container_name,
                        container_tool_path,
                        scope,
                        repo_id,
                        service_name,
                        now,
                        now,
                    ),
                )
                return cur.lastrowid  # type: ignore[return-value]
        except sqlite3.IntegrityError as err:
            if _is_tool_name_conflict(err):
                raise ToolOverrideNameConflict(tool_name) from err
            raise

    def update(
        self,
        tool_name: str,
        *,
        args_mode: Literal["stock", "custom"],
        type: Literal["repo", "api"],
        location: Literal["local", "docker"],
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
        scope: Literal["global", "service"] = "global",
        repo_id: int | None = None,
        service_name: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE tool_overrides SET"
                " args_mode = ?, type = ?, location = ?,"
                " path = ?, container_name = ?, container_tool_path = ?,"
                " scope = ?, repo_id = ?, service_name = ?,"
                " updated_at = ?"
                " WHERE tool_name = ? AND scope = ? AND"
                " COALESCE(repo_id, 0) = COALESCE(?, 0) AND"
                " COALESCE(service_name, '') = COALESCE(?, '')",
                (
                    args_mode,
                    type,
                    location,
                    path,
                    container_name,
                    container_tool_path,
                    scope,
                    repo_id,
                    service_name,
                    now,
                    tool_name,
                    scope,
                    repo_id,
                    service_name,
                ),
            )

    def delete(self, tool_name: str) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "DELETE FROM tool_overrides WHERE tool_name = ?",
                (tool_name,),
            )


def _is_tool_name_conflict(err: sqlite3.IntegrityError) -> bool:
    msg = str(err)
    return "tool_overrides.tool_name" in msg or "uq_tool_overrides" in msg


def _row_to_override(row: sqlite3.Row) -> ToolOverride:
    return ToolOverride(
        id=int(row["id"]),
        tool_name=row["tool_name"],
        args_mode=row["args_mode"],
        type=row["type"],
        location=row["location"],
        path=row["path"],
        container_name=row["container_name"],
        container_tool_path=row["container_tool_path"],
        scope=row["scope"],
        repo_id=row["repo_id"],
        service_name=row["service_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

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
                f"SELECT {_COLUMNS} FROM tool_overrides WHERE tool_name = ?",
                (tool_name,),
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
    ) -> int:
        now = datetime.now(UTC).isoformat()
        try:
            with self._factory.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO tool_overrides ("
                    "tool_name, args_mode, type, location,"
                    " path, container_name, container_tool_path,"
                    " created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tool_name,
                        args_mode,
                        type,
                        location,
                        path,
                        container_name,
                        container_tool_path,
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
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE tool_overrides SET"
                " args_mode = ?, type = ?, location = ?,"
                " path = ?, container_name = ?, container_tool_path = ?,"
                " updated_at = ?"
                " WHERE tool_name = ?",
                (
                    args_mode,
                    type,
                    location,
                    path,
                    container_name,
                    container_tool_path,
                    now,
                    tool_name,
                ),
            )

    def delete(self, tool_name: str) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "DELETE FROM tool_overrides WHERE tool_name = ?",
                (tool_name,),
            )


def _is_tool_name_conflict(err: sqlite3.IntegrityError) -> bool:
    return "tool_overrides.tool_name" in str(err)


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
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

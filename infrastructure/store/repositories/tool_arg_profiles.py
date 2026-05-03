"""SQLite adapter for the ``tool_arg_profiles`` table."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.tool_arg_profiles import (
    ToolArgProfileNameConflict,
    ToolArgProfilesRepositoryPort,
)
from domain.tool_arg_profiles.entry import (
    ToolArgProfile,
    ToolArgProfileArg,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


_COLUMNS = "id, tool_name, name, args, created_at, updated_at"


class ToolArgProfilesRepository(ToolArgProfilesRepositoryPort):
    """CRUD on ``tool_arg_profiles``. JSON ``args`` is opaque at this layer."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def list_paginated(
        self,
        *,
        tool_name: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolArgProfile], int]:
        params: list[Any] = []
        where = ""
        if tool_name is not None:
            where = " WHERE tool_name = ?"
            params.append(tool_name)
        with self._factory.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM tool_arg_profiles{where}",
                tuple(params),
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM tool_arg_profiles{where}"
                " ORDER BY id ASC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [_row_to_profile(r) for r in rows], int(total)

    def get(self, profile_id: int) -> ToolArgProfile | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM tool_arg_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return _row_to_profile(row) if row else None

    def insert(
        self,
        *,
        tool_name: str,
        name: str,
        args: list[ToolArgProfileArg],
    ) -> int:
        now = datetime.now(UTC).isoformat()
        try:
            with self._factory.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO tool_arg_profiles"
                    " (tool_name, name, args, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (tool_name, name, _args_to_json(args), now, now),
                )
                return cur.lastrowid  # type: ignore[return-value]
        except sqlite3.IntegrityError as err:
            if _is_name_conflict(err):
                raise ToolArgProfileNameConflict(tool_name, name) from err
            raise

    def update(
        self,
        profile_id: int,
        *,
        tool_name: str,
        name: str,
        args: list[ToolArgProfileArg],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        try:
            with self._factory.connect() as conn:
                conn.execute(
                    "UPDATE tool_arg_profiles SET"
                    " tool_name = ?, name = ?, args = ?, updated_at = ?"
                    " WHERE id = ?",
                    (tool_name, name, _args_to_json(args), now, profile_id),
                )
        except sqlite3.IntegrityError as err:
            if _is_name_conflict(err):
                raise ToolArgProfileNameConflict(tool_name, name) from err
            raise

    def delete(self, profile_id: int) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "DELETE FROM tool_arg_profiles WHERE id = ?",
                (profile_id,),
            )

    def existing_ids(self, ids: list[int]) -> list[int]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._factory.connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM tool_arg_profiles WHERE id IN ({placeholders})",
                tuple(ids),
            ).fetchall()
        return [int(r["id"]) for r in rows]


def _is_name_conflict(err: sqlite3.IntegrityError) -> bool:
    text = str(err)
    return "tool_arg_profiles.tool_name" in text and "tool_arg_profiles.name" in text


def _args_to_json(args: list[ToolArgProfileArg]) -> str:
    return json.dumps([dataclasses.asdict(arg) for arg in args])


def _args_from_json(raw: str) -> list[ToolArgProfileArg]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError(f"args column must hold a JSON list, got {type(parsed)!r}")
    out: list[ToolArgProfileArg] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            raise ValueError(f"args entry must be a JSON object, got {type(entry)!r}")
        kind = entry.get("type")
        if kind == "flag":
            out.append(ToolArgProfileFlagArg(name=entry["name"]))
        elif kind == "string":
            out.append(
                ToolArgProfileStringArg(name=entry["name"], value=entry["value"])
            )
        elif kind == "file":
            out.append(ToolArgProfileFileArg(name=entry["name"], path=entry["path"]))
        else:
            raise ValueError(f"unknown tool_arg_profile arg type: {kind!r}")
    return out


def _row_to_profile(row: sqlite3.Row) -> ToolArgProfile:
    return ToolArgProfile(
        id=int(row["id"]),
        tool_name=row["tool_name"],
        name=row["name"],
        args=_args_from_json(row["args"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

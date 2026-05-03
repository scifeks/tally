"""SQLite adapter for the ``saved_scans`` family of tables."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.ports.saved_scans import (
    SavedScanNameConflict,
    SavedScansRepositoryPort,
)
from domain.saved_scans.entry import (
    SavedScan,
    SavedScanArgProfileRef,
    SavedScanHydrated,
    SavedScanListItem,
    SavedScanRepoRef,
    SavedScanToolRef,
)

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


_SAVED_SCAN_COLUMNS = "id, name, skip_enrichment, created_at, updated_at"


class SavedScansRepository(SavedScansRepositoryPort):
    """CRUD on ``saved_scans`` with three-join hydration."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def list_for_project(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SavedScanListItem], int]:
        with self._factory.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM saved_scans").fetchone()[0]
            rows = conn.execute(
                f"SELECT {_SAVED_SCAN_COLUMNS} FROM saved_scans"
                " ORDER BY id ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            if not rows:
                return [], int(total)
            ids = [int(r["id"]) for r in rows]
            placeholders = ",".join("?" for _ in ids)
            repo_rows = conn.execute(
                "SELECT saved_scan_id, repo_id FROM saved_scan_repos"
                f" WHERE saved_scan_id IN ({placeholders})"
                " ORDER BY saved_scan_id ASC, repo_id ASC",
                tuple(ids),
            ).fetchall()
            tool_rows = conn.execute(
                "SELECT saved_scan_id, tool_name FROM saved_scan_tools"
                f" WHERE saved_scan_id IN ({placeholders})"
                " ORDER BY saved_scan_id ASC, tool_name ASC",
                tuple(ids),
            ).fetchall()
            profile_rows = conn.execute(
                "SELECT saved_scan_id, arg_profile_id FROM saved_scan_arg_profiles"
                f" WHERE saved_scan_id IN ({placeholders})"
                " ORDER BY saved_scan_id ASC, arg_profile_id ASC",
                tuple(ids),
            ).fetchall()

        repo_ids: dict[int, list[int]] = defaultdict(list)
        for r in repo_rows:
            repo_ids[int(r["saved_scan_id"])].append(int(r["repo_id"]))
        tool_names: dict[int, list[str]] = defaultdict(list)
        for r in tool_rows:
            tool_names[int(r["saved_scan_id"])].append(r["tool_name"])
        arg_profile_ids: dict[int, list[int]] = defaultdict(list)
        for r in profile_rows:
            arg_profile_ids[int(r["saved_scan_id"])].append(int(r["arg_profile_id"]))

        items = [
            SavedScanListItem(
                saved_scan=_row_to_saved_scan(row),
                repo_ids=repo_ids.get(int(row["id"]), []),
                tool_names=tool_names.get(int(row["id"]), []),
                arg_profile_ids=arg_profile_ids.get(int(row["id"]), []),
            )
            for row in rows
        ]
        return items, int(total)

    def get_hydrated(self, saved_scan_id: int) -> SavedScanHydrated | None:
        with self._factory.connect() as conn:
            scan_row = conn.execute(
                f"SELECT {_SAVED_SCAN_COLUMNS} FROM saved_scans WHERE id = ?",
                (saved_scan_id,),
            ).fetchone()
            if scan_row is None:
                return None
            repo_rows = conn.execute(
                "SELECT r.id AS id, r.name AS name, r.deleted_at AS deleted_at"
                " FROM saved_scan_repos j"
                " JOIN repositories r ON r.id = j.repo_id"
                " WHERE j.saved_scan_id = ?"
                " ORDER BY r.id ASC",
                (saved_scan_id,),
            ).fetchall()
            tool_rows = conn.execute(
                "SELECT tool_name FROM saved_scan_tools"
                " WHERE saved_scan_id = ?"
                " ORDER BY tool_name ASC",
                (saved_scan_id,),
            ).fetchall()
            profile_rows = conn.execute(
                "SELECT p.id AS id, p.tool_name AS tool_name, p.name AS name"
                " FROM saved_scan_arg_profiles j"
                " JOIN tool_arg_profiles p ON p.id = j.arg_profile_id"
                " WHERE j.saved_scan_id = ?"
                " ORDER BY p.id ASC",
                (saved_scan_id,),
            ).fetchall()

        return SavedScanHydrated(
            saved_scan=_row_to_saved_scan(scan_row),
            repos=[
                SavedScanRepoRef(
                    id=int(r["id"]),
                    name=r["name"],
                    deleted_at=r["deleted_at"],
                )
                for r in repo_rows
            ],
            tools=[SavedScanToolRef(tool_name=r["tool_name"]) for r in tool_rows],
            arg_profiles=[
                SavedScanArgProfileRef(
                    id=int(r["id"]),
                    tool_name=r["tool_name"],
                    name=r["name"],
                )
                for r in profile_rows
            ],
        )

    def list_arg_profile_ids(self, saved_scan_id: int) -> list[int]:
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT arg_profile_id FROM saved_scan_arg_profiles"
                " WHERE saved_scan_id = ?"
                " ORDER BY arg_profile_id ASC",
                (saved_scan_id,),
            ).fetchall()
        return [int(r["arg_profile_id"]) for r in rows]

    def insert(
        self,
        *,
        name: str,
        skip_enrichment: bool,
        repo_ids: list[int],
        tool_names: list[str],
        arg_profile_ids: list[int],
    ) -> int:
        now = datetime.now(UTC).isoformat()
        try:
            with self._factory.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO saved_scans"
                    " (name, skip_enrichment, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?)",
                    (name, 1 if skip_enrichment else 0, now, now),
                )
                saved_scan_id = int(cur.lastrowid)  # type: ignore[arg-type]
                _write_join_rows(
                    conn,
                    saved_scan_id=saved_scan_id,
                    repo_ids=repo_ids,
                    tool_names=tool_names,
                    arg_profile_ids=arg_profile_ids,
                )
                return saved_scan_id
        except sqlite3.IntegrityError as err:
            if _is_name_conflict(err):
                raise SavedScanNameConflict(name) from err
            raise

    def replace(
        self,
        saved_scan_id: int,
        *,
        name: str,
        skip_enrichment: bool,
        repo_ids: list[int],
        tool_names: list[str],
        arg_profile_ids: list[int],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        try:
            with self._factory.connect() as conn:
                conn.execute(
                    "UPDATE saved_scans SET name = ?, skip_enrichment = ?,"
                    " updated_at = ? WHERE id = ?",
                    (name, 1 if skip_enrichment else 0, now, saved_scan_id),
                )
                conn.execute(
                    "DELETE FROM saved_scan_repos WHERE saved_scan_id = ?",
                    (saved_scan_id,),
                )
                conn.execute(
                    "DELETE FROM saved_scan_tools WHERE saved_scan_id = ?",
                    (saved_scan_id,),
                )
                conn.execute(
                    "DELETE FROM saved_scan_arg_profiles WHERE saved_scan_id = ?",
                    (saved_scan_id,),
                )
                _write_join_rows(
                    conn,
                    saved_scan_id=saved_scan_id,
                    repo_ids=repo_ids,
                    tool_names=tool_names,
                    arg_profile_ids=arg_profile_ids,
                )
        except sqlite3.IntegrityError as err:
            if _is_name_conflict(err):
                raise SavedScanNameConflict(name) from err
            raise

    def delete(self, saved_scan_id: int) -> None:
        with self._factory.connect() as conn:
            conn.execute("DELETE FROM saved_scans WHERE id = ?", (saved_scan_id,))


def _write_join_rows(
    conn: sqlite3.Connection,
    *,
    saved_scan_id: int,
    repo_ids: list[int],
    tool_names: list[str],
    arg_profile_ids: list[int],
) -> None:
    if repo_ids:
        conn.executemany(
            "INSERT INTO saved_scan_repos (saved_scan_id, repo_id) VALUES (?, ?)",
            [(saved_scan_id, rid) for rid in repo_ids],
        )
    if tool_names:
        conn.executemany(
            "INSERT INTO saved_scan_tools (saved_scan_id, tool_name) VALUES (?, ?)",
            [(saved_scan_id, name) for name in tool_names],
        )
    if arg_profile_ids:
        conn.executemany(
            "INSERT INTO saved_scan_arg_profiles"
            " (saved_scan_id, arg_profile_id) VALUES (?, ?)",
            [(saved_scan_id, pid) for pid in arg_profile_ids],
        )


def _is_name_conflict(err: sqlite3.IntegrityError) -> bool:
    return "saved_scans.name" in str(err)


def _row_to_saved_scan(row: sqlite3.Row) -> SavedScan:
    return SavedScan(
        id=int(row["id"]),
        name=row["name"],
        skip_enrichment=bool(row["skip_enrichment"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

"""RunRepository: manages scan_runs and run_tools tables."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.run_repository import RunRepositoryPort
from domain.scans.entry import SCAN_RUN_STATUSES, ScanRunRow, ToolRunRow

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


class RunRepository(RunRepositoryPort):
    """Manages scan run lifecycle records (`scan_runs` + `run_tools`)."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------
    # Legacy entry points (retained for REPL parity and existing tests)
    # ------------------------------------------------------------------
    def create_run(self, args: dict) -> int:
        """Insert a scan_run row with only the legacy fields populated.

        Used by the REPL `_create_sqlite_run` path before Phase 5.2
        wires the full create() signature. New columns remain NULL so
        the row is still queryable but does not yet participate in
        status/event tracking.
        """
        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO scan_runs (args, created_at) VALUES (?, ?)",
                (json.dumps(args), created_at),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def add_run_tools(self, run_id: int, tools: list[dict]) -> None:
        """Insert one row per tool for a run (legacy minimal columns)."""
        with self._factory.connect() as conn:
            conn.executemany(
                "INSERT INTO run_tools (run_id, tool, findings_count) VALUES (?, ?, ?)",
                [
                    (run_id, t.get("tool", ""), t.get("findings_count", 0))
                    for t in tools
                ],
            )

    # ------------------------------------------------------------------
    # Phase 5.1 surface
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        project_id: int,
        repo_ids: list[str],
        tool_ids: list[str],
        domains: list[str],
        skip_enrichment: bool,
        args: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> int:
        """Insert a fully-populated scan_runs row. Returns the new id."""
        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO scan_runs ("
                "project_id, args, created_at, status,"
                " repo_ids, tool_ids, domains, skip_enrichment"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    json.dumps(args or {}),
                    created_at,
                    status,
                    json.dumps(repo_ids),
                    json.dumps(tool_ids),
                    json.dumps(domains),
                    1 if skip_enrichment else 0,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def set_status(self, run_id: int, status: str) -> None:
        if status not in SCAN_RUN_STATUSES:
            raise ValueError(f"unknown scan_run status: {status!r}")
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE scan_runs SET status = ? WHERE id = ?",
                (status, run_id),
            )

    def set_started_at(self, run_id: int, when: str | None = None) -> None:
        ts = when or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE scan_runs SET started_at = ? WHERE id = ?",
                (ts, run_id),
            )

    def set_finished_at(self, run_id: int, when: str | None = None) -> None:
        ts = when or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE scan_runs SET finished_at = ? WHERE id = ?",
                (ts, run_id),
            )

    def set_findings_count(self, run_id: int, count: int) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE scan_runs SET findings_count = ? WHERE id = ?",
                (count, run_id),
            )

    def mark_stale_runs_failed(self) -> int:
        """Mark every ``running``/``cancelling`` row as ``failed``.

        Used at server start to clean up rows whose owning process is
        gone. Tier-1 lock guarantees only one scan is live at a time,
        so any persisted-as-running row from a prior process is stale.
        Returns the row count updated.
        """
        ts = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "UPDATE scan_runs SET status = 'failed', finished_at = ?"
                " WHERE status IN ('running', 'cancelling')"
                "   AND finished_at IS NULL",
                (ts,),
            )
            return cur.rowcount

    def get(self, run_id: int) -> ScanRunRow | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scan_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return _row_to_scan_run(row) if row else None

    def latest_run_id(self) -> int | None:
        """Return the highest scan_runs.id in this project's DB, or None.

        Used by the triage dispatch path: triage operates on the most
        recent scan run in the project. Choice is made by the
        application core, never by the API or REPL caller. The
        repository is already project-scoped via its ConnectionFactory,
        so no explicit project_id filter is required.
        """
        with self._factory.connect() as conn:
            row = conn.execute("SELECT MAX(id) FROM scan_runs").fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    def list_for_project(
        self,
        project_id: int,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ScanRunRow], int]:
        """Paginated list, newest-first. Returns (rows, total_count)."""
        params: list[Any] = [project_id]
        where = "project_id = ?"
        if status is not None:
            where += " AND status = ?"
            params.append(status)
        with self._factory.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM scan_runs WHERE {where}",
                tuple(params),
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM scan_runs WHERE {where}"
                " ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [_row_to_scan_run(r) for r in rows], int(total)

    def get_with_tool_runs(
        self, run_id: int
    ) -> tuple[ScanRunRow, list[ToolRunRow]] | None:
        with self._factory.connect() as conn:
            scan_row = conn.execute(
                "SELECT * FROM scan_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if scan_row is None:
                return None
            tool_rows = conn.execute(
                "SELECT * FROM run_tools WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return (
            _row_to_scan_run(scan_row),
            [_row_to_tool_run(r) for r in tool_rows],
        )

    def add_tool_run(
        self,
        *,
        run_id: int,
        tool: str,
        repo: str | None = None,
        domain: str | None = None,
        status: str = "queued",
    ) -> int:
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO run_tools (run_id, tool, repo, domain, status)"
                " VALUES (?, ?, ?, ?, ?)",
                (run_id, tool, repo, domain, status),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update_tool_run(
        self,
        tool_run_id: int,
        *,
        status: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        exit_code: int | None = None,
        skip_reason: str | None = None,
        findings_count: int | None = None,
        enriched_count: int | None = None,
        total_to_enrich: int | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if started_at is not None:
            sets.append("started_at = ?")
            params.append(started_at)
        if finished_at is not None:
            sets.append("finished_at = ?")
            params.append(finished_at)
        if exit_code is not None:
            sets.append("exit_code = ?")
            params.append(exit_code)
        if skip_reason is not None:
            sets.append("skip_reason = ?")
            params.append(skip_reason)
        if findings_count is not None:
            sets.append("findings_count = ?")
            params.append(findings_count)
        if enriched_count is not None:
            sets.append("enriched_count = ?")
            params.append(enriched_count)
        if total_to_enrich is not None:
            sets.append("total_to_enrich = ?")
            params.append(total_to_enrich)
        if not sets:
            return
        params.append(tool_run_id)
        with self._factory.connect() as conn:
            conn.execute(
                f"UPDATE run_tools SET {', '.join(sets)} WHERE id = ?",
                tuple(params),
            )


def _parse_json_list(val: Any) -> list[str]:
    if val is None or val == "":
        return []
    try:
        parsed = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _parse_json_dict(val: Any) -> dict[str, Any]:
    if val is None or val == "":
        return {}
    try:
        parsed = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_to_scan_run(row: Any) -> ScanRunRow:
    return ScanRunRow(
        id=row["id"],
        project_id=row["project_id"],
        args=_parse_json_dict(row["args"]),
        created_at=row["created_at"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        repo_ids=_parse_json_list(row["repo_ids"]),
        tool_ids=_parse_json_list(row["tool_ids"]),
        domains=_parse_json_list(row["domains"]),
        skip_enrichment=bool(row["skip_enrichment"]),
        findings_count=row["findings_count"],
    )


def _row_to_tool_run(row: Any) -> ToolRunRow:
    return ToolRunRow(
        id=row["id"],
        run_id=row["run_id"],
        tool=row["tool"],
        findings_count=int(row["findings_count"] or 0),
        repo=row["repo"],
        domain=row["domain"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        exit_code=row["exit_code"],
        skip_reason=row["skip_reason"],
        enriched_count=row["enriched_count"],
        total_to_enrich=row["total_to_enrich"],
    )

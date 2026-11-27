"""RunRepository: manages scan_runs and run_tools tables."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.run_repository import RunRepositoryPort
from domain.scans.entry import (
    SCAN_RUN_STATUSES,
    TOOL_RUN_STATUSES,
    ScanRunRow,
    ToolRunRow,
)

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


class RunRepository(RunRepositoryPort):
    """Manages scan run lifecycle records (`scan_runs` + `run_tools`)."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # Legacy entry points (retained for REPL parity and existing tests)
    def create_run(self, args: dict) -> int:
        """Insert a scan_run row with only legacy fields populated.

        New columns remain NULL; the row is queryable but does not
        participate in status/event tracking. Retained for backward
        compatibility with the REPL.
        """
        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO scan_runs (args, created_at) VALUES (?, ?)",
                (json.dumps(args), created_at),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    # Full scan run creation
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
        saved_scan_id: int | None = None,
        arg_profile_snapshots: dict[str, str] | None = None,
    ) -> int:
        """Insert a fully-populated scan_runs row. Returns the new id."""
        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO scan_runs ("
                "project_id, args, created_at, status,"
                " repo_ids, tool_ids, domains, skip_enrichment,"
                " saved_scan_id, arg_profile_snapshots"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    json.dumps(args or {}),
                    created_at,
                    status,
                    json.dumps(repo_ids),
                    json.dumps(tool_ids),
                    json.dumps(domains),
                    1 if skip_enrichment else 0,
                    saved_scan_id,
                    _snapshots_json(arg_profile_snapshots),
                ),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

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
        stale = "status IN ('running', 'cancelling') AND finished_at IS NULL"
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE run_tools SET status = 'failed',"
                " reason = 'scan interrupted',"
                " finished_at = COALESCE(finished_at, ?)"
                " WHERE status = 'running' AND run_id IN"
                f" (SELECT id FROM scan_runs WHERE {stale})",
                (ts,),
            )
            cur = conn.execute(
                "UPDATE scan_runs SET status = 'failed', finished_at = ?"
                f" WHERE {stale}",
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
                "SELECT rt.*, r.name AS repo_name FROM run_tools rt"
                " LEFT JOIN repositories r ON r.id = rt.repo_id"
                " WHERE rt.run_id = ? ORDER BY rt.id ASC",
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
        repo_id: int | None = None,
        service: str | None = None,
        domain: str | None = None,
        status: str = "running",
        started_at: str | None = None,
        finished_at: str | None = None,
        reason: str | None = None,
    ) -> int:
        _require_tool_run_status(status)
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO run_tools (run_id, tool, repo_id, service, domain,"
                " status, started_at, finished_at, reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    tool,
                    repo_id,
                    service,
                    domain,
                    status,
                    started_at,
                    finished_at,
                    reason,
                ),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    def update_tool_run(
        self,
        tool_run_id: int,
        *,
        status: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        exit_code: int | None = None,
        reason: str | None = None,
        findings_count: int | None = None,
        enriched_count: int | None = None,
        total_to_enrich: int | None = None,
    ) -> None:
        if status is not None:
            _require_tool_run_status(status)
        given = {
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": exit_code,
            "reason": reason,
            "findings_count": findings_count,
            "enriched_count": enriched_count,
            "total_to_enrich": total_to_enrich,
        }
        changes = {col: val for col, val in given.items() if val is not None}
        if not changes:
            return
        assignments = ", ".join(f"{col} = ?" for col in changes)
        with self._factory.connect() as conn:
            conn.execute(
                f"UPDATE run_tools SET {assignments} WHERE id = ?",
                (*changes.values(), tool_run_id),
            )

    def delete_tool_run(self, tool_run_id: int) -> None:
        with self._factory.connect() as conn:
            conn.execute("DELETE FROM run_tools WHERE id = ?", (tool_run_id,))

    def fail_running_tool_runs(self, run_id: int, reason: str) -> int:
        ts = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "UPDATE run_tools SET status = 'failed', reason = ?,"
                " finished_at = COALESCE(finished_at, ?)"
                " WHERE run_id = ? AND status = 'running'",
                (reason, ts, run_id),
            )
            return cur.rowcount

    def count_findings_for_run_tool(self, run_id: int, tool: str) -> int:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE run_id = ? AND tool = ?",
                (run_id, tool),
            ).fetchone()
        return int(row[0])

    def latest_done_run_id(
        self, *, repo_id: int, service: str | None, tool: str
    ) -> int | None:
        # IS compares null-safely, so a null service matches null rows.
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT MAX(run_id) FROM run_tools"
                " WHERE repo_id = ? AND service IS ? AND tool = ?"
                " AND status = 'done'",
                (repo_id, service, tool),
            ).fetchone()
        return None if row[0] is None else int(row[0])

    def list_repo_tool_pairs(self, run_id: int) -> list[tuple[int | None, str]]:
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT repo_id, tool FROM run_tools"
                " WHERE run_id = ? ORDER BY repo_id, tool",
                (run_id,),
            ).fetchall()
        return [(r["repo_id"], r["tool"]) for r in rows]


def _snapshots_json(snapshots: dict[str, str] | None) -> str | None:
    if not snapshots:
        return None
    return json.dumps({tool: json.loads(args) for tool, args in snapshots.items()})


def _require_tool_run_status(status: str) -> None:
    if status not in TOOL_RUN_STATUSES:
        raise ValueError(f"unknown tool run status: {status!r}")


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
        repo_id=row["repo_id"],
        repo_name=row["repo_name"],
        service=row["service"],
        domain=row["domain"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        exit_code=row["exit_code"],
        reason=row["reason"],
        enriched_count=row["enriched_count"],
        total_to_enrich=row["total_to_enrich"],
    )

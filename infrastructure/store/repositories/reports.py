"""CRUD and retention helpers for the reports table.

Each row tracks one report-generation run with its lifecycle status
(queued, running, done, failed, cancelling, cancelled), filesystem path
for streaming downloads, and retention tier (auto or pinned).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.report_repository import ReportRepositoryPort
from domain.reports.entry import REPORT_STATUSES, ReportRow

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


RETENTION_TIERS = ("auto", "pinned")


class ReportRepository(ReportRepositoryPort):
    """CRUD + retention helpers for the project-scoped ``reports`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def create(
        self,
        *,
        project_id: int,
        scan_run_id: int | None,
        format: str,
        filename: str,
        filepath: str,
        status: str = "queued",
        retention_tier: str = "auto",
        display_name: str | None = None,
    ) -> int:
        if status not in REPORT_STATUSES:
            raise ValueError(f"unknown report status: {status!r}")
        if retention_tier not in RETENTION_TIERS:
            raise ValueError(f"unknown retention_tier: {retention_tier!r}")
        display_name = display_name or datetime.now(UTC).date().isoformat()
        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO reports ("
                "project_id, scan_run_id, format, filename, filepath,"
                " status, retention_tier, display_name, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    scan_run_id,
                    format,
                    filename,
                    filepath,
                    status,
                    retention_tier,
                    display_name,
                    created_at,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def set_status(self, report_id: int, status: str) -> None:
        if status not in REPORT_STATUSES:
            raise ValueError(f"unknown report status: {status!r}")
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE reports SET status = ? WHERE id = ?",
                (status, report_id),
            )

    def set_started_at(self, report_id: int, when: str | None = None) -> None:
        ts = when or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE reports SET started_at = ? WHERE id = ?",
                (ts, report_id),
            )

    def set_finished_at(self, report_id: int, when: str | None = None) -> None:
        ts = when or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE reports SET finished_at = ? WHERE id = ?",
                (ts, report_id),
            )

    def set_file_size(self, report_id: int, size: int) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE reports SET file_size_bytes = ? WHERE id = ?",
                (size, report_id),
            )

    def set_error(self, report_id: int, message: str) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE reports SET error = ? WHERE id = ?",
                (message, report_id),
            )

    def set_pinned(self, report_id: int, pinned: bool) -> None:
        tier = "pinned" if pinned else "auto"
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE reports SET retention_tier = ? WHERE id = ?",
                (tier, report_id),
            )

    def delete(self, report_id: int) -> None:
        with self._factory.connect() as conn:
            conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))

    def update_metadata(
        self,
        report_id: int,
        project_id: int,
        *,
        display_name: str | None = None,
        notes: str | None = None,
    ) -> ReportRow | None:
        sets: list[str] = []
        params: list[Any] = []
        if display_name is not None:
            sets.append("display_name = ?")
            params.append(display_name)
        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)
        if not sets:
            return self.get(report_id)
        params.extend([report_id, project_id])
        with self._factory.connect() as conn:
            conn.execute(
                f"UPDATE reports SET {', '.join(sets)} WHERE id = ? AND project_id = ?",
                tuple(params),
            )
            row = conn.execute(
                "SELECT * FROM reports WHERE id = ? AND project_id = ?",
                (report_id, project_id),
            ).fetchone()
        return _row_to_report(row) if row else None

    def get(self, report_id: int) -> ReportRow | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
        return _row_to_report(row) if row else None

    def list_for_project(
        self,
        project_id: int,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ReportRow], int]:
        params: list[Any] = [project_id]
        where = "project_id = ?"
        if status is not None:
            where += " AND status = ?"
            params.append(status)
        with self._factory.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM reports WHERE {where}",
                tuple(params),
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM reports WHERE {where}"
                " ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [_row_to_report(r) for r in rows], int(total)

    def latest_for_project(self, project_id: int) -> ReportRow | None:
        """Return the most recent ``done`` report for *project_id*, or None."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports"
                " WHERE project_id = ? AND status = 'done'"
                " ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return _row_to_report(row) if row else None

    def select_for_retention(
        self,
        project_id: int,
        *,
        keep: int,
    ) -> list[ReportRow]:
        """Return ``done`` rows older than the *keep*-th most-recent.

        Pinned rows are always preserved. Returns rows the caller should
        delete from disk and from the table. Newest-first ordering is
        preserved so the first ``keep`` rows survive.
        """
        if keep < 0:
            raise ValueError("keep must be non-negative")
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reports"
                " WHERE project_id = ?"
                "   AND status = 'done'"
                "   AND retention_tier = 'auto'"
                " ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        all_rows = [_row_to_report(r) for r in rows]
        if len(all_rows) <= keep:
            return []
        return all_rows[keep:]


def _row_to_report(row: Any) -> ReportRow:
    return ReportRow(
        id=row["id"],
        project_id=row["project_id"],
        scan_run_id=row["scan_run_id"],
        format=row["format"],
        filename=row["filename"],
        filepath=row["filepath"],
        status=row["status"],
        retention_tier=row["retention_tier"],
        file_size_bytes=row["file_size_bytes"],
        error=row["error"],
        display_name=row["display_name"],
        notes=row["notes"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )

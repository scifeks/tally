"""TriageBatchRepository: triage batch lifecycle management."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from application.ports.triage_batch_repository import TriageBatchRepositoryPort
from domain.triage.entry import TriageBatchRow, TriageRunSummary

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


TRIAGE_BATCH_STATUSES = (
    "pending",
    "in_progress",
    "completed",
    "failed",
    "cancelled",
)


class TriageBatchRepository(TriageBatchRepositoryPort):
    """Manages the triage_batches table lifecycle."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def fetch_active_findings_for_batching(
        self, run_id: int, tool: str, repo: str, segment: str
    ) -> list[dict[str, Any]]:
        """Return the active findings for *tool*/*repo*/*segment* in batching order.

        Only the ``sast`` and ``web`` segments produce rows; every other segment
        returns an empty list.
        """
        params = (run_id, segment, tool, repo)
        if segment == "sast":
            sql = """
                SELECT
                    f.id, r.name AS repo, f.file, f.tool,
                    f.rule_id, f.severity, f.confidence,
                    f.description, f.cwe,
                    json_extract(f.meta, '$.line_start')
                        AS line_start,
                    json_extract(f.meta, '$.code_snippet')
                        AS code_snippet,
                    json_extract(f.meta, '$.risk_type')
                        AS risk_type,
                    json_extract(f.meta, '$.owasp')
                        AS owasp
                FROM findings f
                JOIN repositories r ON f.repo_id = r.id
                WHERE f.run_id = ?
                  AND f.segment = ?
                  AND f.tool = ?
                  AND r.name = ?
                  AND f.status = 'active'
                ORDER BY
                    f.severity ASC,
                    f.file,
                    CAST(
                        json_extract(f.meta, '$.line_start')
                        AS INTEGER
                    )
            """
        elif segment == "web":
            sql = """
                SELECT
                    f.id, r.name AS repo, f.url, f.tool,
                    f.rule_id, f.severity, f.confidence,
                    f.description, f.cwe AS cwe_id,
                    json_extract(f.meta, '$.alert_name')
                        AS alert_name,
                    json_extract(f.meta, '$.method')
                        AS method,
                    json_extract(f.meta, '$.evidence')
                        AS evidence,
                    json_extract(f.meta, '$.risk_type')
                        AS risk_type,
                    json_extract(f.meta, '$.param')
                        AS param,
                    json_extract(f.meta, '$.attack')
                        AS attack,
                    json_extract(f.meta, '$.remediation')
                        AS remediation,
                    json_extract(f.meta, '$.fingerprint_type')
                        AS fingerprint_type
                FROM findings f
                JOIN repositories r ON f.repo_id = r.id
                WHERE f.run_id = ?
                  AND f.segment = ?
                  AND f.tool = ?
                  AND r.name = ?
                  AND f.status = 'active'
                ORDER BY
                    f.severity ASC,
                    f.url
            """
        else:
            return []

        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def create_batches(
        self, run_id: int, batches: list[list[dict[str, Any]]]
    ) -> list[tuple[int, int]]:
        """Persist pre-built triage *batches* for *run_id*.

        Returns ``[(batch_id, finding_count), ...]`` for each inserted
        row.
        """
        if not batches:
            return []

        result: list[tuple[int, int]] = []
        with self._factory.connect() as conn:
            for batch in batches:
                cur = conn.execute(
                    "INSERT INTO triage_batches"
                    " (run_id, finding_ids, batch_data, status,"
                    " run_attempts)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        run_id,
                        json.dumps([f["id"] for f in batch]),
                        json.dumps(batch),
                        "pending",
                        0,
                    ),
                )
                batch_id: int = cur.lastrowid  # type: ignore[assignment]
                result.append((batch_id, len(batch)))
        return result

    def claim_batch(self, run_id: int) -> TriageBatchRow | None:
        """Atomically claim the next pending batch for *run_id*.

        Returns ``None`` if no claimable batch exists.
        """
        with self._factory.connect() as conn:
            row = conn.execute(
                """
                UPDATE triage_batches
                SET
                    status       = 'in_progress',
                    started_at   = datetime('now'),
                    run_attempts = run_attempts + 1
                WHERE id = (
                    SELECT id FROM triage_batches
                    WHERE  status = 'pending'
                      AND  run_id = ?
                    ORDER BY id ASC
                    LIMIT 1
                )
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_triage_batch(row)

    def complete_batch(self, batch_id: int, status: str) -> None:
        """Sets status and completed_at on the given batch."""
        with self._factory.connect() as conn:
            conn.execute(
                """
                UPDATE triage_batches
                SET status = ?, completed_at = datetime('now')
                WHERE id = ?
                """,
                (status, batch_id),
            )

    def reset_for_resume(self, run_id: int) -> int:
        """Flip stranded ``in_progress`` and ``failed`` rows back
        to ``pending`` so an explicit resume can pick them up.

        Returns the number of rows flipped.
        """
        with self._factory.connect() as conn:
            cur = conn.execute(
                "UPDATE triage_batches"
                " SET status = 'pending', started_at = NULL"
                " WHERE run_id = ?"
                "   AND status IN ('in_progress', 'failed')",
                (run_id,),
            )
            return cur.rowcount

    def get_active_finding_combos(
        self, run_id: int, skip_tools: frozenset[str]
    ) -> list[tuple[str, str, str]]:
        """Return distinct (tool, repo_name, segment) tuples for active findings.

        Excludes any tool in skip_tools. Findings without a repo_id are
        omitted (legacy unlinked rows).
        """
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT f.tool, r.name, f.segment"
                " FROM findings f"
                " JOIN repositories r ON f.repo_id = r.id"
                " WHERE f.run_id = ? AND f.status = 'active' AND f.segment IS NOT NULL",
                (run_id,),
            ).fetchall()
        return [
            (r["tool"], r["name"], r["segment"])
            for r in rows
            if r["tool"] not in skip_tools
        ]

    def cancel_remaining(self, run_id: int) -> int:
        """Mark remaining pending/in_progress batches as cancelled.

        Sets ``status = 'cancelled'`` and stamps ``completed_at`` to now
        for every triage_batches row whose status is ``pending`` or
        ``in_progress``. Returns the number of rows updated.
        """
        with self._factory.connect() as conn:
            cur = conn.execute(
                "UPDATE triage_batches"
                " SET status = 'cancelled', completed_at = datetime('now')"
                " WHERE run_id = ? AND status IN ('pending', 'in_progress')",
                (run_id,),
            )
            return cur.rowcount

    def list_run_ids_for_project(
        self, *, offset: int = 0, limit: int = 20
    ) -> tuple[list[int], int]:
        """Return distinct run_ids with triage_batches rows, newest-first."""
        with self._factory.connect() as conn:
            total = conn.execute(
                "SELECT COUNT(DISTINCT run_id) FROM triage_batches"
                " WHERE run_id IS NOT NULL",
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT DISTINCT run_id FROM triage_batches"
                " WHERE run_id IS NOT NULL"
                " ORDER BY run_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [int(r["run_id"]) for r in rows], int(total)

    def list_for_run(
        self,
        run_id: int,
        *,
        include_cancelled: bool = False,
        after_batch_id: int | None = None,
    ) -> list[TriageBatchRow]:
        """Return triage_batches rows for *run_id*, ordered by id.

        Canceled batches are excluded by default. That shape is only
        useful to the resume path, which treats canceled rows as
        prior-attempt relics. Display-time callers must pass
        ``include_cancelled=True`` to see the true state of the run.

        ``after_batch_id`` narrows the view to a single triage attempt:
        the client captures ``MAX(id)`` at Reset/Start time and later
        reads only batches with ``id > after_batch_id``.
        """
        clauses = ["run_id = ?"]
        params: list[object] = [run_id]
        if not include_cancelled:
            clauses.append("status != 'cancelled'")
        if after_batch_id is not None:
            clauses.append("id > ?")
            params.append(after_batch_id)
        sql = (
            "SELECT * FROM triage_batches"
            f" WHERE {' AND '.join(clauses)}"
            " ORDER BY id ASC"
        )
        with self._factory.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_triage_batch(r) for r in rows]

    def summarize_for_run(
        self, run_id: int, *, after_batch_id: int | None = None
    ) -> TriageRunSummary | None:
        """Aggregate view of a triage run derived from its batches.

        Returns ``None`` if no triage_batches rows exist for *run_id*.

        - status: ``'cancelled'`` if any batch cancelled; else
          ``'failed'`` if any batch failed; else ``'running'`` if any
          batch still pending/in_progress; else ``'done'``.
        - started_at: MIN(started_at) across batches, or None if not
          yet started.
        - finished_at: MAX(completed_at) iff terminal (no
          pending/in_progress batches remain).
        - total_findings: sum of ``len(finding_ids)`` across all
          batches for this run.
        - processed_findings: same sum but only over batches whose
          status is ``'completed'``.

        See ``list_for_run`` for what ``after_batch_id`` means.
        """
        rows = self.list_for_run(
            run_id, include_cancelled=True, after_batch_id=after_batch_id
        )
        if not rows:
            return None

        counts: dict[str, int] = dict.fromkeys(TRIAGE_BATCH_STATUSES, 0)
        total_findings = 0
        processed_findings = 0
        started_candidates: list[str] = []
        completed_candidates: list[str] = []
        for r in rows:
            counts[r.status] = counts.get(r.status, 0) + 1
            total_findings += len(r.finding_ids)
            if r.status == "completed":
                processed_findings += len(r.finding_ids)
            if r.started_at:
                started_candidates.append(r.started_at)
            if r.completed_at:
                completed_candidates.append(r.completed_at)

        if counts.get("cancelled", 0) > 0:
            status = "cancelled"
        elif counts.get("pending", 0) > 0 or counts.get("in_progress", 0) > 0:
            status = "running"
        elif counts.get("failed", 0) > 0:
            status = "failed"
        else:
            status = "done"

        terminal = counts.get("pending", 0) == 0 and counts.get("in_progress", 0) == 0
        started_at = min(started_candidates) if started_candidates else None
        finished_at = (
            max(completed_candidates) if (terminal and completed_candidates) else None
        )

        return TriageRunSummary(
            scan_run_id=run_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            total_findings=total_findings,
            processed_findings=processed_findings,
            total_batches=len(rows),
            counts_by_status=counts,
        )

    def max_batch_id_for_run(self, run_id: int) -> int | None:
        """Return ``MAX(id)`` across all triage_batches rows for *run_id*.

        ``None`` when no rows exist yet. Used by the Reset/Start path
        so the client can capture a per-attempt boundary.
        """
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT MAX(id) AS max_id FROM triage_batches WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None or row["max_id"] is None:
            return None
        return int(row["max_id"])


def _row_to_triage_batch(row: Any) -> TriageBatchRow:
    return TriageBatchRow(
        id=row["id"],
        run_id=row["run_id"],
        finding_ids=json.loads(row["finding_ids"]) if row["finding_ids"] else [],
        batch_data=json.loads(row["batch_data"]) if row["batch_data"] else [],
        status=row["status"],
        run_attempts=int(row["run_attempts"] or 0),
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )

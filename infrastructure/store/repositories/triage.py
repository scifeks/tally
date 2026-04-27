"""TriageBatchRepository — triage batch lifecycle management."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


TRIAGE_BATCH_STATUSES = (
    "pending",
    "in_progress",
    "completed",
    "failed",
    "cancelled",
)


@dataclass(frozen=True)
class TriageBatchRow:
    id: int
    run_id: int
    finding_ids: list[int]
    batch_data: list[dict]
    status: str
    run_attempts: int
    created_at: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class TriageRunSummary:
    """Aggregate view of a triage run derived from triage_batches rows."""

    scan_run_id: int
    status: str
    started_at: str | None
    finished_at: str | None
    total_findings: int
    processed_findings: int
    total_batches: int
    counts_by_status: dict[str, int]


class TriageBatchRepository:
    """Manages the triage_batches table lifecycle."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def create_batches(self, run_id: int, tool: str, repo: str, segment: str) -> int:
        """Fetch active findings, compute batches, and persist to triage_batches.

        Returns the number of batches written.
        """
        from application.triage.batching import compute_batches

        params = (segment, tool, repo)
        if segment == "api":
            sql = """
                SELECT
                    f.id, r.name AS repo, f.url, f.tool,
                    f.severity, f.confidence, f.description,
                    json_extract(f.meta, '$.remediation') AS remediation,
                    json_extract(f.meta, '$.method') AS method,
                    json_extract(f.meta, '$.param') AS param,
                    json_extract(f.meta, '$.evidence') AS evidence,
                    json_extract(f.meta, '$.risk_type') AS risk_type,
                    json_extract(f.meta, '$.cwe_id') AS cwe_id,
                    json_extract(f.meta, '$.alert_name') AS alert_name
                FROM findings f
                JOIN repositories r ON f.repo_id = r.id
                WHERE f.segment = ? AND f.tool = ? AND r.name = ?
                  AND f.status = 'active'
                ORDER BY f.severity ASC, f.url,
                         json_extract(f.meta, '$.risk_type')
            """
        elif segment == "sast":
            sql = """
                SELECT
                    f.id, r.name AS repo, f.file, f.tool,
                    f.rule_id, f.severity, f.confidence,
                    f.description, f.cwe,
                    json_extract(f.meta, '$.line_start') AS line_start,
                    json_extract(f.meta, '$.code_snippet') AS code_snippet,
                    json_extract(f.meta, '$.risk_type') AS risk_type,
                    json_extract(f.meta, '$.owasp') AS owasp
                FROM findings f
                JOIN repositories r ON f.repo_id = r.id
                WHERE f.segment = ? AND f.tool = ? AND r.name = ?
                  AND f.status = 'active'
                ORDER BY
                    f.severity ASC,
                    f.file,
                    CAST(json_extract(f.meta, '$.line_start') AS INTEGER)
            """
        else:
            return 0

        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        findings = [dict(row) for row in rows]

        batches = compute_batches(findings)
        if not batches:
            return 0

        insert_rows = [
            (
                run_id,
                json.dumps([f["id"] for f in batch]),
                json.dumps(batch),
                "pending",
                0,
            )
            for batch in batches
        ]
        with self._factory.connect() as conn:
            conn.executemany(
                "INSERT INTO triage_batches"
                " (run_id, finding_ids, batch_data, status, run_attempts)"
                " VALUES (?, ?, ?, ?, ?)",
                insert_rows,
            )
        return len(batches)

    def claim_batch(self, run_id: int) -> dict | None:
        """Atomically claims the next pending batch for *run_id*.

        Returns the batch row as a dict (with JSON columns parsed) or None
        if no claimable batch exists.
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
                    WHERE  status       = 'pending'
                      AND  run_attempts < 3
                      AND  run_id       = ?
                    ORDER BY id ASC
                    LIMIT 1
                )
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["batch_data"] = json.loads(result["batch_data"])
        result["finding_ids"] = json.loads(result["finding_ids"])
        return result

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

    def reset_stale_batches(self, run_id: int) -> int:
        """Reset in_progress batches for run_id back to pending.

        Returns the number of batches reset.
        """
        with self._factory.connect() as conn:
            cur = conn.execute(
                "UPDATE triage_batches"
                " SET status = 'pending', started_at = NULL"
                " WHERE status = 'in_progress' AND run_id = ?",
                (run_id,),
            )
            return cur.rowcount

    def reset_for_resume(self, run_id: int) -> int:
        """Flip stranded ``in_progress`` and retryable ``failed`` rows back
        to ``pending`` so an explicit resume can pick them up.

        ``run_attempts`` is preserved — the existing 3-attempt cap in
        ``claim_batch`` still applies. Returns the number of rows flipped.
        """
        with self._factory.connect() as conn:
            cur = conn.execute(
                "UPDATE triage_batches"
                " SET status = 'pending', started_at = NULL"
                " WHERE run_id = ?"
                "   AND ("
                "     status = 'in_progress'"
                "     OR (status = 'failed' AND run_attempts < 3)"
                "   )",
                (run_id,),
            )
            return cur.rowcount

    def get_active_finding_combos(
        self, skip_tools: frozenset[str]
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
                " WHERE f.status = 'active' AND f.segment IS NOT NULL",
            ).fetchall()
        return [
            (r["tool"], r["name"], r["segment"])
            for r in rows
            if r["tool"] not in skip_tools
        ]

    # ------------------------------------------------------------------
    # Phase 6 — query/aggregation helpers for the API surface
    # ------------------------------------------------------------------

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
        """Distinct run_ids that have triage_batches rows, newest-first.

        ``triage_batches`` lives in the project's findings.db, so the
        repository instance is already project-scoped — there is no
        project_id column to filter on. Returns (rows, total_count).
        """
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

    def list_for_run(self, run_id: int) -> list[TriageBatchRow]:
        """Return all triage_batches rows for *run_id*, ordered by id."""
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM triage_batches WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [_row_to_triage_batch(r) for r in rows]

    def summarize_for_run(self, run_id: int) -> TriageRunSummary | None:
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
          status is in (``'completed'``, ``'failed'``,
          ``'cancelled'``).
        """
        rows = self.list_for_run(run_id)
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
            if r.status in ("completed", "failed", "cancelled"):
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

"""TriageBatchRepository — triage batch lifecycle management."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


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
                    id, repo, url, tool, severity, confidence, description,
                    json_extract(meta, '$.remediation') AS remediation,
                    json_extract(meta, '$.method') AS method,
                    json_extract(meta, '$.param') AS param,
                    json_extract(meta, '$.evidence') AS evidence,
                    json_extract(meta, '$.risk_type') AS risk_type,
                    json_extract(meta, '$.cwe_id') AS cwe_id,
                    json_extract(meta, '$.alert_name') AS alert_name
                FROM findings
                WHERE segment = ? AND tool = ? AND repo = ? AND status = 'active'
                ORDER BY severity DESC, url, json_extract(meta, '$.risk_type')
            """
        elif segment == "sast":
            sql = """
                SELECT
                    id, repo, file, tool, rule_id, severity, confidence,
                    description, cwe,
                    json_extract(meta, '$.line_start') AS line_start,
                    json_extract(meta, '$.code_snippet') AS code_snippet,
                    json_extract(meta, '$.risk_type') AS risk_type,
                    json_extract(meta, '$.owasp') AS owasp
                FROM findings
                WHERE segment = ? AND tool = ? AND repo = ? AND status = 'active'
                ORDER BY
                    severity DESC,
                    file,
                    CAST(json_extract(meta, '$.line_start') AS INTEGER)
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

    def get_active_finding_combos(
        self, skip_tools: frozenset[str]
    ) -> list[tuple[str, str, str]]:
        """Return distinct (tool, repo, segment) tuples for active, segmented findings.

        Excludes any tool in skip_tools.
        """
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT tool, repo, segment FROM findings"
                " WHERE status = 'active' AND segment IS NOT NULL",
            ).fetchall()
        return [
            (r["tool"], r["repo"], r["segment"])
            for r in rows
            if r["tool"] not in skip_tools
        ]

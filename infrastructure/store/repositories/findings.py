"""Create, read, update, and search findings in SQLite."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from application.ports.finding_repository import FindingRepositoryPort
from domain.findings.entry import Finding
from domain.findings.normalization import NormalizedFinding
from domain.findings.severity import Severity
from infrastructure.store.repositories.findings_query import FindingQueryBuilder
from infrastructure.store.repositories.findings_serial import deserialise_row

if TYPE_CHECKING:
    import sqlite3

    from infrastructure.store.connection import ConnectionFactory

logger = logging.getLogger(__name__)


class FindingRepository(FindingRepositoryPort):
    """CRUD and search operations for the findings table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def insert_findings(self, run_id: int, findings: list[NormalizedFinding]) -> None:
        """Insert finding rows from a scan, mapping ChromaDB fields to schema."""
        if not findings:
            return

        rows: list[tuple] = []
        for finding in findings:
            columns = finding.columns
            meta = finding.meta
            fingerprint = finding.fingerprint

            repo_id_raw = columns.get("repo_id")
            repo_id_val: int | None
            if isinstance(repo_id_raw, int):
                repo_id_val = repo_id_raw
            elif isinstance(repo_id_raw, str) and repo_id_raw.isdigit():
                repo_id_val = int(repo_id_raw)
            else:
                repo_id_val = None

            rows.append(
                (
                    fingerprint,
                    run_id,
                    columns.get("tool"),
                    columns.get("domain"),
                    columns.get("segment"),
                    repo_id_val,
                    columns.get("finding_type"),
                    columns.get("severity"),
                    columns.get("confidence"),
                    columns.get("file"),
                    columns.get("rule_id"),
                    columns.get("url"),
                    columns.get("vulnerability_id"),
                    columns.get("package_name"),
                    columns.get("ecosystem"),
                    columns.get("description"),
                    columns.get("package_version"),
                    columns.get("cwe"),
                    0,
                    json.dumps(meta),
                )
            )

        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        rows_with_ts = [(*row, now, now, 1, "active", 0) for row in rows]

        sql = """
            INSERT INTO findings (
                fingerprint, run_id, tool, domain, segment,
                repo_id, finding_type, severity,
                confidence, file, rule_id, url,
                vulnerability_id, package_name, ecosystem,
                description, package_version, cwe,
                enriched, meta,
                first_seen, last_seen, seen_count,
                status, should_report
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """
        with self._factory.connect() as conn:
            conn.executemany(sql, rows_with_ts)

    def delete_findings(self, tools: list[str] | None = None) -> None:
        """Delete findings, scoping to specific tools when provided."""
        if tools is not None:
            return self.delete_findings_by_tool_name(tools)

        with self._factory.connect() as conn:
            conn.execute("DELETE FROM triage_batches")
            conn.execute("DELETE FROM tool_audit_log")
            conn.execute("DELETE FROM findings")
            conn.execute("DELETE FROM run_tools")
            conn.execute("DELETE FROM scan_runs")

    def delete_findings_by_tool_name(self, tools: list[str]) -> None:
        """Delete findings and related triage/audit rows for the given tools."""
        if not tools:
            return

        placeholders = ",".join("?" * len(tools))

        with self._factory.connect() as conn:
            # Collect finding IDs being deleted (for triage_batch cleanup)
            rows = conn.execute(
                f"SELECT id FROM findings WHERE tool IN ({placeholders})",
                tools,
            ).fetchall()
            deleted_finding_ids = {row["id"] for row in rows}

            conn.execute(
                f"DELETE FROM findings WHERE tool IN ({placeholders})",
                tools,
            )

            # Delete triage_batches where ALL finding_ids are in the deleted set
            all_batches = conn.execute(
                "SELECT id, finding_ids FROM triage_batches"
            ).fetchall()
            batch_ids_to_delete = []
            for batch in all_batches:
                batch_finding_ids = json.loads(batch["finding_ids"])
                if batch_finding_ids and all(
                    fid in deleted_finding_ids for fid in batch_finding_ids
                ):
                    batch_ids_to_delete.append(batch["id"])

            if batch_ids_to_delete:
                batch_placeholders = ",".join("?" * len(batch_ids_to_delete))
                conn.execute(
                    f"DELETE FROM triage_batches WHERE id IN ({batch_placeholders})",
                    batch_ids_to_delete,
                )

            conn.execute(
                f"DELETE FROM tool_audit_log WHERE tool_name IN ({placeholders})",
                tools,
            )

    def get_tool_meta_keys(
        self, tool_name: str, sample: int = 200
    ) -> tuple[int, set[str]]:
        """Return (total_row_count, union_of_meta_keys) for tool_name."""
        with self._factory.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE tool = ?", (tool_name,)
            ).fetchone()[0]
            if count == 0:
                return 0, set()
            rows = conn.execute(
                "SELECT meta FROM findings WHERE tool = ? LIMIT ?",
                (tool_name, sample),
            ).fetchall()
        keys: set[str] = set()
        for row in rows:
            try:
                keys.update(json.loads(row[0] or "{}").keys())
            except (json.JSONDecodeError, TypeError):
                pass
        return count, keys

    def _get_row(self, finding_id: int) -> dict | None:
        """Return the raw findings row dict by primary key, or None."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def get_finding(self, finding_id: int) -> Finding | None:
        """Return a single finding by primary key, or None if not found."""
        row = self._get_row(finding_id)
        return Finding.from_row(row) if row is not None else None

    def _build_findings_filter(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if segments:
            placeholders = ",".join("?" * len(segments))
            clauses.append(f"segment IN ({placeholders})")
            params.extend(segments)
        if require_file:
            clauses.append("(file IS NOT NULL AND file != '')")
        if tools:
            placeholders = ",".join("?" * len(tools))
            clauses.append(f"tool IN ({placeholders})")
            params.extend(tools)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def get_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Finding]:
        """Return findings matching optional filters, capped at *limit* rows."""
        where, base_params = self._build_findings_filter(
            tools=tools,
            domain=domain,
            status=status,
            segments=segments,
            require_file=require_file,
        )
        params: list[object] = list(base_params) + [limit, offset]
        sql = (
            f"SELECT * FROM findings {where}"
            " ORDER BY first_seen DESC, id DESC"
            " LIMIT ? OFFSET ?"
        )
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Finding.from_row(r) for r in rows]

    def count_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
    ) -> int:
        """Return total count of findings matching the given filters."""
        where, params = self._build_findings_filter(
            tools=tools,
            domain=domain,
            status=status,
            segments=segments,
            require_file=require_file,
        )
        sql = f"SELECT COUNT(*) FROM findings {where}"
        with self._factory.connect() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def _insert_history(
        self,
        conn: sqlite3.Connection,
        finding_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        source: str,
        inference_context: dict[str, Any] | None = None,
    ) -> None:
        from datetime import UTC, datetime

        conn.execute(
            "INSERT INTO finding_history"
            " (finding_id, timestamp, before_values, after_values,"
            "  inference_context, source)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                finding_id,
                datetime.now(UTC).isoformat(),
                json.dumps(before),
                json.dumps(after),
                json.dumps(inference_context)
                if inference_context is not None
                else None,
                source,
            ),
        )

    def update_finding(
        self,
        finding_id: int,
        severity_rank: int,
        confidence: str,
        finding_type_json: str,
        triage_meta: dict,
        strategy: str,
        *,
        triaged_by: str = "claudecode",
        source: str = "auto_triage",
    ) -> bool:
        """Update enrichment fields on a finding row.

        Returns True on success.  Raises ValueError if the finding is not found.
        """
        from datetime import UTC, datetime

        row = self._get_row(finding_id)
        if row is None:
            raise ValueError(f"Finding {finding_id} not found")
        previous_confidence = row["confidence"]
        existing_meta = json.loads(row["meta"] or "{}")
        now_iso = datetime.now(UTC).isoformat()
        existing_meta["triage"] = {
            **triage_meta,
            "previous_confidence": previous_confidence,
            "triaged_by": triaged_by,
            "triaged_at": now_iso,
            "strategy": strategy,
        }
        before = dict(row)
        updated_meta = json.dumps(existing_meta)
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE findings "
                "SET confidence = ?, "
                "    finding_type = ?, "
                "    severity = ?, "
                "    enriched = 1, "
                "    last_seen = ?, "
                "    triaged_at = ?, "
                "    triaged_by = ?, "
                "    meta = ? "
                "WHERE id = ?",
                (
                    confidence,
                    finding_type_json,
                    severity_rank,
                    now_iso,
                    now_iso,
                    triaged_by,
                    updated_meta,
                    finding_id,
                ),
            )
            after_row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            self._insert_history(
                conn, finding_id, before, dict(after_row) if after_row else {}, source
            )
        return True

    def get_reportable_findings(self) -> list[Finding]:
        """Return findings confirmed by triage and marked for the report."""
        sql = (
            "SELECT * FROM findings WHERE triaged_by IS NOT NULL AND should_report = 1"
        )
        with self._factory.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [Finding.from_row(r) for r in rows]

    def get_findings_marked_for_report(self) -> list[Finding]:
        """Return findings marked for inclusion regardless of triage status."""
        sql = "SELECT * FROM findings WHERE should_report = 1"
        with self._factory.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [Finding.from_row(r) for r in rows]

    def get_all_findings(self) -> list[Finding]:
        """Return all findings with no triage filter."""
        with self._factory.connect() as conn:
            rows = conn.execute("SELECT * FROM findings").fetchall()
        return [Finding.from_row(r) for r in rows]

    def get_findings_by_run_id(self, run_id: int) -> list[Finding]:
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        return [Finding.from_row(r) for r in rows]

    def get_all_findings_deserialized(self) -> list[dict]:
        """Return all findings with no triage filter, deserialized."""
        with self._factory.connect() as conn:
            rows = conn.execute("SELECT * FROM findings").fetchall()
        return [deserialise_row(r) for r in rows]

    def update_analyst_fields(
        self,
        finding_id: int,
        columns: dict[str, Any],
        meta: dict[str, Any],
        *,
        source: str = "web_ui",
    ) -> bool:
        """Update analyst-writable fields, setting triaged_by and triaged_at."""
        from datetime import UTC, datetime

        row = self._get_row(finding_id)
        if row is None:
            return False

        try:
            existing_meta: dict[str, Any] = json.loads(row["meta"] or "{}")
        except (json.JSONDecodeError, TypeError):
            existing_meta = {}

        existing_meta.update(meta)
        updated_meta = json.dumps(existing_meta)
        now_iso = datetime.now(UTC).isoformat()

        set_parts: list[str] = []
        params: list[Any] = []

        for col, val in columns.items():
            set_parts.append(f"{col} = ?")
            params.append(val)

        set_parts.extend(["meta = ?", "triaged_by = 'analyst_web'", "triaged_at = ?"])
        params.extend([updated_meta, now_iso])
        params.append(finding_id)

        before = dict(row)
        sql = f"UPDATE findings SET {', '.join(set_parts)} WHERE id = ?"
        with self._factory.connect() as conn:
            cursor = conn.execute(sql, params)
            if cursor.rowcount > 0:
                after_row = conn.execute(
                    "SELECT * FROM findings WHERE id = ?", (finding_id,)
                ).fetchone()
                self._insert_history(
                    conn,
                    finding_id,
                    before,
                    dict(after_row) if after_row else {},
                    source,
                )
            return cursor.rowcount > 0

    def batch_update_analyst_fields(
        self,
        ids: list[int],
        fields: dict[str, Any],
    ) -> int:
        """Update analyst fields on multiple findings, return updated count."""
        from datetime import UTC, datetime

        if not ids or not fields:
            return 0

        now_iso = datetime.now(UTC).isoformat()

        set_parts: list[str] = []
        params: list[Any] = []
        for col, val in fields.items():
            set_parts.append(f"{col} = ?")
            if col == "severity" and val is not None:
                params.append(Severity.from_label(str(val)).rank)
            else:
                params.append(val)
        set_parts.extend(["triaged_by = 'analyst_web'", "triaged_at = ?"])
        params.append(now_iso)

        placeholders = ",".join("?" * len(ids))
        params.extend(ids)

        sql = f"UPDATE findings SET {', '.join(set_parts)} WHERE id IN ({placeholders})"
        with self._factory.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def reset_tal_ids(self) -> None:
        """Set tal_id = NULL for every row in findings."""
        with self._factory.connect() as conn:
            conn.execute("UPDATE findings SET tal_id = NULL")

    def bulk_update_tal_ids(self, pairs: list[tuple[str, int]]) -> None:
        """Persist TAL-IDs for a set of findings.

        Args:
            pairs: List of (tal_id, finding_id) tuples.
        """
        if not pairs:
            return
        sql = "UPDATE findings SET tal_id = ? WHERE id = ?"
        with self._factory.connect() as conn:
            conn.executemany(sql, pairs)

    def get_ids_by_fingerprints(
        self, fingerprints: list[str], run_id: int | None = None
    ) -> list[int]:
        """Return SQLite findings.id values for the given fingerprints.

        When ``run_id`` is provided, only rows from that run are considered.
        Fingerprints are non-unique across runs, so multiple rows may share
        the same fingerprint value.

        All matching ids are returned (there may be more than one per
        fingerprint). Missing fingerprints are silently omitted.
        """
        if not fingerprints:
            return []
        unique_fps = list(set(fingerprints))
        placeholders = ",".join("?" * len(unique_fps))
        if run_id is not None:
            sql = (
                f"SELECT id FROM findings"
                f" WHERE fingerprint IN ({placeholders})"
                f" AND run_id = ?"
            )
            params: list = unique_fps + [run_id]
        else:
            sql = f"SELECT id FROM findings WHERE fingerprint IN ({placeholders})"
            params = unique_fps
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [row["id"] for row in rows]

    def get_by_ids(self, ids: list[int]) -> list[dict]:
        """Return deserialized row dicts for the given SQLite primary keys."""
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        sql = f"SELECT * FROM findings WHERE id IN ({placeholders})"
        with self._factory.connect() as conn:
            rows = conn.execute(sql, ids).fetchall()
        result: list[dict] = []
        for row in rows:
            d = deserialise_row(row)
            d["id"] = row["id"]
            result.append(d)
        return result

    def update_enrichment_fields(
        self,
        finding_id: int,
        columns: dict[str, Any],
        meta: dict[str, Any],
        *,
        source: str = "llm_inference",
    ) -> None:
        """Write LLM-enriched fields back to the SQLite row."""
        from datetime import UTC, datetime

        row = self._get_row(finding_id)
        if row is None:
            return

        try:
            existing_meta: dict[str, Any] = json.loads(row["meta"] or "{}")
        except (json.JSONDecodeError, TypeError):
            existing_meta = {}

        existing_meta.update(meta)

        before = dict(row)
        updated_meta = json.dumps(existing_meta)
        now_iso = datetime.now(UTC).isoformat()

        set_parts: list[str] = ["enriched = 1", "last_seen = ?", "meta = ?"]
        params: list[Any] = [now_iso, updated_meta]

        for col, val in columns.items():
            set_parts.append(f"{col} = ?")
            params.append(val)

        params.append(finding_id)
        sql_upd = f"UPDATE findings SET {', '.join(set_parts)} WHERE id = ?"
        with self._factory.connect() as conn:
            conn.execute(sql_upd, params)
            after_row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            self._insert_history(
                conn,
                finding_id,
                before,
                dict(after_row) if after_row else {},
                source,
            )

    def search(self, filters: dict) -> list[dict]:
        """Execute a structured SQL search and return ChromaDB-shaped results."""
        sql, params = FindingQueryBuilder(filters).build()
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"metadata": deserialise_row(row), "distance": None, "document": ""}
            for row in rows
        ]

    def search_raw(self, filters: dict) -> list[Finding]:
        """Execute a structured SQL search; return parsed Finding rows.

        Unlike search(), rows are not wrapped in ChromaDB-shaped result
        envelopes; callers receive Finding instances.
        """
        sql, params = FindingQueryBuilder(filters).build()
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Finding.from_row(row) for row in rows]

    def search_count(self, filters: dict) -> int:
        """Return the total row count matching *filters* (no pagination)."""
        sql, params = FindingQueryBuilder(filters).build_count()
        with self._factory.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def count_aggregates(self) -> dict:
        """Return finding counts and dashboard aggregates across dimensions."""
        canonical_statuses = ("active", "false_positive", "fixed", "wont_fix")
        canonical_severities = (
            "critical",
            "high",
            "medium",
            "low",
            "informational",
        )

        with self._factory.connect() as conn:
            by_severity: dict[str, int] = {}
            for rank, count in conn.execute(
                "SELECT severity, COUNT(*) FROM findings"
                " WHERE severity IS NOT NULL GROUP BY severity"
            ).fetchall():
                by_severity[Severity.from_rank(rank).label] = count

            by_domain: dict[str, int] = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT domain, COUNT(*) FROM findings"
                    " WHERE domain IS NOT NULL GROUP BY domain"
                ).fetchall()
            }
            by_segment: dict[str, int] = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT segment, COUNT(*) FROM findings"
                    " WHERE segment IS NOT NULL GROUP BY segment"
                ).fetchall()
            }
            by_repo: dict[str, int] = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT r.name, COUNT(*) FROM findings f"
                    " JOIN repositories r ON f.repo_id = r.id"
                    " WHERE f.repo_id IS NOT NULL GROUP BY f.repo_id"
                ).fetchall()
            }
            by_status: dict[str, int] = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT status, COUNT(*) FROM findings"
                    " WHERE status IS NOT NULL GROUP BY status"
                ).fetchall()
            }
            by_tool: dict[str, int] = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT tool, COUNT(*) FROM findings"
                    " WHERE tool IS NOT NULL GROUP BY tool"
                ).fetchall()
            }

            # Pre-populate canonical cells at 0 so the crosstab is dense.
            by_severity_status: dict[str, dict[str, int]] = {
                sev: dict.fromkeys(canonical_statuses, 0)
                for sev in canonical_severities
            }
            for rank, status, count in conn.execute(
                "SELECT severity, status, COUNT(*) FROM findings"
                " WHERE severity IS NOT NULL AND status IS NOT NULL"
                " GROUP BY severity, status"
            ).fetchall():
                sev_label = Severity.from_rank(rank).label
                row = by_severity_status.setdefault(
                    sev_label, dict.fromkeys(canonical_statuses, 0)
                )
                row[status] = count

            (total_row,) = conn.execute("SELECT COUNT(*) FROM findings").fetchone()
            total = int(total_row or 0)

            (scans_row,) = conn.execute(
                "SELECT COUNT(DISTINCT run_id) FROM findings WHERE run_id IS NOT NULL"
            ).fetchone()
            scans_count = int(scans_row or 0)

            (repos_row,) = conn.execute(
                "SELECT COUNT(DISTINCT repo_id) FROM findings WHERE repo_id IS NOT NULL"
            ).fetchone()
            repos_count = int(repos_row or 0)

            (urls_row,) = conn.execute("SELECT COUNT(*) FROM url_findings").fetchone()
            urls_count = int(urls_row or 0)

            (last_scan_row,) = conn.execute(
                "SELECT MAX(sr.created_at) FROM scan_runs sr"
                " JOIN findings f ON f.run_id = sr.id"
            ).fetchone()
            last_scan_at = last_scan_row

            (last_triage_row,) = conn.execute(
                "SELECT MAX(triaged_at) FROM findings WHERE triaged_at IS NOT NULL"
            ).fetchone()
            last_triage_at = last_triage_row

        return {
            "by_severity": by_severity,
            "by_domain": by_domain,
            "by_segment": by_segment,
            "by_repo": by_repo,
            "by_status": by_status,
            "by_tool": by_tool,
            "by_severity_status": by_severity_status,
            "total": total,
            "scans_count": scans_count,
            "repos_count": repos_count,
            "urls_count": urls_count,
            "last_scan_at": last_scan_at,
            "last_triage_at": last_triage_at,
        }

    def distinct_facet_values(self) -> dict:
        """Return distinct values per filter dimension for UI dropdowns."""
        with self._factory.connect() as conn:
            domains = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT domain FROM findings WHERE domain IS NOT NULL"
                ).fetchall()
            )
            severity_ranks = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT severity FROM findings WHERE severity IS NOT NULL"
                ).fetchall()
            )
            severities = [Severity.from_rank(r).label for r in severity_ranks]
            statuses = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT status FROM findings WHERE status IS NOT NULL"
                ).fetchall()
            )
            confidence_levels = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT confidence FROM findings"
                    " WHERE confidence IS NOT NULL"
                ).fetchall()
            )
            finding_types = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT je.value FROM findings,"
                    " json_each(findings.finding_type) AS je"
                    " WHERE je.value IS NOT NULL"
                ).fetchall()
            )
            tools = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT tool FROM findings WHERE tool IS NOT NULL"
                ).fetchall()
            )
            repos = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT r.name FROM findings f"
                    " JOIN repositories r ON f.repo_id = r.id"
                    " WHERE f.repo_id IS NOT NULL"
                ).fetchall()
            )
            segments = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT segment FROM findings WHERE segment IS NOT NULL"
                ).fetchall()
            )
        return {
            "domains": domains,
            "severities": severities,
            "statuses": statuses,
            "confidence_levels": confidence_levels,
            "finding_types": finding_types,
            "tools": tools,
            "repos": repos,
            "segments": segments,
        }

    def filter_options(self, filters: dict) -> dict:
        """Return per-dimension option counts under the given filter set."""
        builder = FindingQueryBuilder(filters)
        where_parts, params = builder.build_where_parts()

        def _where(extra: str) -> str:
            return " WHERE " + " AND ".join([*where_parts, extra])

        with self._factory.connect() as conn:
            severity: list[dict[str, Any]] = [
                {
                    "value": Severity.from_rank(rank).label,
                    "count": int(count),
                }
                for rank, count in conn.execute(
                    "SELECT severity, COUNT(*) FROM findings"
                    + _where("severity IS NOT NULL")
                    + " GROUP BY severity HAVING COUNT(*) > 0"
                    " ORDER BY severity",
                    params,
                ).fetchall()
            ]

            def _scalar(col: str) -> list[dict[str, Any]]:
                return [
                    {"value": value, "count": int(count)}
                    for value, count in conn.execute(
                        f"SELECT {col}, COUNT(*) FROM findings"
                        + _where(f"{col} IS NOT NULL")
                        + f" GROUP BY {col} HAVING COUNT(*) > 0"
                        f" ORDER BY {col}",
                        params,
                    ).fetchall()
                ]

            status = _scalar("status")
            confidence = _scalar("confidence")
            domain = _scalar("domain")
            segment = _scalar("segment")
            tool = _scalar("tool")

            finding_type: list[dict[str, Any]] = [
                {"value": value, "count": int(count)}
                for value, count in conn.execute(
                    "SELECT je.value, COUNT(DISTINCT findings.id)"
                    " FROM findings, json_each(findings.finding_type) AS je"
                    + _where("je.value IS NOT NULL")
                    + " GROUP BY je.value"
                    " HAVING COUNT(DISTINCT findings.id) > 0"
                    " ORDER BY je.value",
                    params,
                ).fetchall()
            ]

            repo: list[dict[str, Any]] = [
                {"value": int(rid), "label": name, "count": int(count)}
                for rid, name, count in conn.execute(
                    "SELECT findings.repo_id, repositories.name, COUNT(*)"
                    " FROM findings"
                    " JOIN repositories"
                    " ON findings.repo_id = repositories.id"
                    + _where("findings.repo_id IS NOT NULL")
                    + " GROUP BY findings.repo_id, repositories.name"
                    " HAVING COUNT(*) > 0"
                    " ORDER BY repositories.name",
                    params,
                ).fetchall()
            ]

        return {
            "severity": severity,
            "status": status,
            "confidence": confidence,
            "domain": domain,
            "segment": segment,
            "tool": tool,
            "finding_type": finding_type,
            "repo": repo,
        }

    def insert_manual_finding(
        self,
        columns: dict[str, Any],
        meta: dict[str, Any],
        fingerprint: str,
    ) -> int:
        """Insert a single manually-created finding. Returns the new row id."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        row = (
            fingerprint,
            None,  # run_id
            columns.get("tool"),
            columns.get("domain"),
            columns.get("segment"),
            columns.get("repo_id"),
            columns.get("finding_type"),
            columns.get("severity"),
            columns.get("confidence"),
            columns.get("file"),
            columns.get("rule_id"),
            columns.get("url"),
            columns.get("vulnerability_id"),
            columns.get("package_name"),
            columns.get("ecosystem"),
            columns.get("description"),
            columns.get("package_version"),
            columns.get("cwe"),
            0,  # enriched
            json.dumps(meta),
            now,  # first_seen
            now,  # last_seen
            1,  # seen_count
            columns.get("status", "active"),
            0,  # should_report
        )
        sql = """
            INSERT INTO findings (
                fingerprint, run_id, tool, domain, segment,
                repo_id, finding_type, severity, confidence,
                file, rule_id, url, vulnerability_id,
                package_name, ecosystem, description,
                package_version, cwe, enriched, meta,
                first_seen, last_seen, seen_count, status,
                should_report
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """
        with self._factory.connect() as conn:
            cursor = conn.execute(sql, row)
            return cursor.lastrowid  # type: ignore[return-value]

    def delete_finding_by_id(self, finding_id: int) -> None:
        """Delete a single finding by primary key."""
        with self._factory.connect() as conn:
            conn.execute(
                "DELETE FROM findings WHERE id = ?",
                (finding_id,),
            )

"""FindingRepository — CRUD and search for the findings table."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from infrastructure.store.repositories.findings_query import FindingQueryBuilder
from infrastructure.store.repositories.findings_serial import (
    _CHROMA_TO_SQLITE,
    _COMMA_LIST_FIELDS,
    compute_fingerprint,
    deserialise_row,
    normalise_cwe,
    normalise_finding_type,
)

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FindingRepository
# ---------------------------------------------------------------------------


class FindingRepository:
    """CRUD and search operations for the findings table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def upsert_findings(self, run_id: int, findings: list[dict]) -> None:
        """Insert or update findings rows.

        For each finding:

        - Computes a per-tool fingerprint (sha256).
        - Maps known ChromaDB field names to named SQLite columns.
        - Converts comma-joined list fields to JSON arrays in the meta blob.
        - Stores all remaining fields in the meta JSON blob.
        - Sets ``enriched = 1`` on every row.

        Wrapped in a single transaction.
        """
        if not findings:
            return

        # Keys handled before the generic loop — excluded from meta blob.
        _PRE_EXTRACTED: frozenset[str] = frozenset(
            {"finding_type", "cwe", "cwe_id", "cwe_ids"}
        )

        rows: list[tuple] = []
        for finding in findings:
            fingerprint = compute_fingerprint(finding)
            named: dict[str, Any] = {}
            meta: dict[str, Any] = {}

            # --- Pre-extract finding_type ---
            named["finding_type"] = normalise_finding_type(finding.get("finding_type"))

            # --- Pre-extract cwe (any of the three source keys) ---
            raw_cwe = (
                finding.get("cwe") or finding.get("cwe_id") or finding.get("cwe_ids")
            )
            if raw_cwe is not None:
                named["cwe"] = normalise_cwe(raw_cwe)

            # --- Generic column mapping (skip pre-extracted keys) ---
            for key, val in finding.items():
                if key in _PRE_EXTRACTED:
                    continue
                col = _CHROMA_TO_SQLITE.get(key)
                if col is not None:
                    # file_path takes priority over lockfile for the file column.
                    if col == "file" and key == "lockfile":
                        if named.get("file") is None:
                            named["file"] = str(val) if val is not None else None
                    else:
                        named[col] = str(val) if val is not None else None
                else:
                    if key in _COMMA_LIST_FIELDS and isinstance(val, str) and val:
                        meta[key] = [v.strip() for v in val.split(",") if v.strip()]
                    else:
                        meta[key] = val

            rows.append(
                (
                    fingerprint,
                    run_id,
                    named.get("tool"),
                    named.get("domain"),
                    named.get("segment"),
                    named.get("repo"),
                    named.get("finding_type"),
                    named.get("severity"),
                    named.get("confidence"),
                    named.get("file"),
                    named.get("rule_id"),
                    named.get("url"),
                    named.get("host"),
                    named.get("port"),
                    named.get("vulnerability_id"),
                    named.get("package_name"),
                    named.get("ecosystem"),
                    named.get("description"),
                    named.get("package_version"),
                    named.get("cwe"),
                    1,  # enriched
                    json.dumps(meta),
                )
            )

        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        rows_with_ts = [(*row, now, now, 1, "active") for row in rows]

        sql = """
            INSERT INTO findings (
                fingerprint, run_id, tool, domain, segment, repo,
                finding_type, severity,
                confidence, file, rule_id, url, host, port,
                vulnerability_id, package_name, ecosystem,
                description, package_version, cwe, enriched, meta,
                first_seen, last_seen, seen_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?)
            ON CONFLICT (fingerprint) DO UPDATE SET
                run_id          = excluded.run_id,
                severity        = excluded.severity,
                confidence      = excluded.confidence,
                description     = excluded.description,
                package_version = excluded.package_version,
                cwe             = excluded.cwe,
                enriched        = excluded.enriched,
                meta            = excluded.meta,
                last_seen       = excluded.last_seen,
                seen_count      = COALESCE(seen_count, 0) + 1
        """
        with self._factory.connect() as conn:
            conn.executemany(sql, rows_with_ts)

    def delete_findings(self, tools: list[str] | None = None) -> None:
        """Delete findings from the store.

        ``tools=None``   — DELETE all rows from findings, run_tools, run_repos,
                           and runs.
        ``tools=[...]``  — DELETE FROM findings WHERE tool IN (...).
                           Does NOT delete run / run_tools / run_repos rows.
        """
        with self._factory.connect() as conn:
            if tools is None:
                conn.execute("DELETE FROM findings")
                conn.execute("DELETE FROM run_tools")
                conn.execute("DELETE FROM run_repos")
                conn.execute("DELETE FROM runs")
            else:
                placeholders = ",".join("?" * len(tools))
                conn.execute(
                    f"DELETE FROM findings WHERE tool IN ({placeholders})",
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

    def get_finding(self, finding_id: int) -> dict | None:
        """Return a single finding row by primary key, or None if not found."""
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def get_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        repo: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
        limit: int = 10,
    ) -> list[dict]:
        """Return findings matching optional filters, capped at *limit* rows."""
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
        if repo:
            clauses.append("repo = ?")
            params.append(repo)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        sql = f"SELECT * FROM findings {where} LIMIT ?"
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_finding(
        self,
        finding_id: int,
        confidence: str,
        finding_type: str,
        severity: str,
        reasoning: str,
        remediation: str,
        attack_vector: str | None,
        call_stack: str | None,
        strategy: str,
    ) -> bool:
        """Update enrichment fields on a finding row.

        Returns True on success.  Raises ValueError if the finding is not found.
        """
        from datetime import UTC, datetime

        row = self.get_finding(finding_id)
        if row is None:
            raise ValueError(f"Finding {finding_id} not found")
        previous_confidence = row["confidence"]
        existing_meta = json.loads(row["meta"] or "{}")
        now_iso = datetime.now(UTC).isoformat()
        existing_meta["triage"] = {
            "confidence": confidence,
            "previous_confidence": previous_confidence,
            "reasoning": reasoning,
            "remediation": remediation,
            "attack_vector": attack_vector,
            "call_stack": call_stack,
            "triaged_by": "claude-code",
            "triaged_at": now_iso,
            "strategy": strategy,
        }
        updated_meta = json.dumps(existing_meta)
        finding_type_db = json.dumps([finding_type])
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE findings "
                "SET confidence = ?, "
                "    finding_type = ?, "
                "    severity = ?, "
                "    enriched = 1, "
                "    last_seen = ?, "
                "    triaged_at = ?, "
                "    triaged_by = 'claude-code', "
                "    meta = ? "
                "WHERE id = ?",
                (
                    confidence,
                    finding_type_db,
                    severity,
                    now_iso,
                    now_iso,
                    updated_meta,
                    finding_id,
                ),
            )
        return True

    def get_reportable_findings(self) -> list[dict]:
        """Return findings where triaged_by IS NOT NULL and should_report = 1.

        These are the findings that have been confirmed by triage and are
        marked for inclusion in the report.
        """
        sql = (
            "SELECT * FROM findings WHERE triaged_by IS NOT NULL AND should_report = 1"
        )
        with self._factory.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def get_all_findings(self) -> list[dict]:
        """Return all findings with no triage filter."""
        with self._factory.connect() as conn:
            rows = conn.execute("SELECT * FROM findings").fetchall()
        return [dict(r) for r in rows]

    def get_all_nmap_findings(self) -> list[dict]:
        """Return all nmap findings with no triage filter.

        Nmap findings are always informational reconnaissance data and are
        never subject to triage filtering — they are queried in full for the
        Network Surface section of the report.
        """
        sql = "SELECT * FROM findings WHERE tool = 'nmap'"
        with self._factory.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

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

    def search(self, filters: dict) -> list[dict]:
        """Execute a structured SQL search.

        ``filters`` format::

            {
                "conditions": [(col_expr, op, values), ...],
                "page": 1,
                "page_size": 200,
            }

        Returns a list of result dicts::

            {"metadata": {<chromadb-compatible field names>}, "distance": None}
        """
        sql, params = FindingQueryBuilder(filters).build()
        with self._factory.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"metadata": deserialise_row(row), "distance": None, "document": ""}
            for row in rows
        ]

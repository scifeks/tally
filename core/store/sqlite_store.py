"""SQLite structured findings store for tally security findings."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.tools.constants import FINDING_TYPES

logger = logging.getLogger(__name__)

_FINGERPRINT_REGISTRY: dict[str, Callable[[dict[str, Any]], str]] | None = None


def _generic_fingerprint_key(finding: dict[str, Any]) -> str:
    safe = {
        k: v for k, v in sorted(finding.items()) if isinstance(v, (str, int, float))
    }
    return json.dumps(safe, sort_keys=True)


def _get_fingerprint_registry() -> dict[str, Callable[[dict[str, Any]], str]]:
    global _FINGERPRINT_REGISTRY
    if _FINGERPRINT_REGISTRY is None:
        from core.rag.ingestor import get_fingerprint_registry

        _FINGERPRINT_REGISTRY = get_fingerprint_registry()
    return _FINGERPRINT_REGISTRY


# ---------------------------------------------------------------------------
# Column mappings
# ---------------------------------------------------------------------------

# ChromaDB field name → SQLite named column name
_CHROMA_TO_SQLITE: dict[str, str] = {
    "tool": "tool",
    "domain": "domain",
    "segment": "segment",
    "repo": "repo",
    "finding_type": "finding_type",
    "severity": "severity",
    "confidence": "confidence",
    "file_path": "file",
    "rule_id": "rule_id",
    "url": "url",
    "ip_address": "host",
    "port": "port",
    "vulnerability_id": "vulnerability_id",
    "package_name": "package_name",
    "ecosystem": "ecosystem",
    "description": "description",
    "package_version": "package_version",
    "lockfile": "file",  # SCA: lower priority than file_path
}

# Named column names that are identical in ChromaDB and SQLite
_DIRECT_COLUMNS: tuple[str, ...] = (
    "tool",
    "domain",
    "segment",
    "repo",
    "severity",
    "confidence",
    "rule_id",
    "url",
    "port",
    "vulnerability_id",
    "package_name",
    "ecosystem",
    "description",
    "package_version",
)

# Comma-joined string fields in ChromaDB → stored as JSON arrays in meta
_COMMA_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "technology",
        "subcategory",
        "references",
        "aliases",
        "tags",
        "ssh_algorithms",
    }
)

# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _compute_fingerprint(finding: dict[str, Any]) -> str:
    """Compute a stable sha256 fingerprint from per-tool key fields."""
    tool = finding.get("tool", "")
    key_fn = _get_fingerprint_registry().get(tool, _generic_fingerprint_key)
    key = key_fn(finding)
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalise_finding_type(val: Any) -> str | None:
    """Normalise finding_type to a JSON array string, e.g. '["secret"]'."""
    if val is None:
        return None
    if isinstance(val, str) and val.startswith("["):
        try:
            items = json.loads(val)
        except json.JSONDecodeError:
            items = [val]
    elif isinstance(val, list):
        items = val
    else:
        items = [str(val)]
    valid = [v for v in items if v in FINDING_TYPES]
    for bad in (v for v in items if v not in FINDING_TYPES):
        logger.warning("Invalid finding_type value %r; skipping", bad)
    return json.dumps(valid) if valid else None


def _normalise_cwe(val: Any) -> str | None:
    """Normalise a CWE value to a JSON array string, e.g. '["CWE-89"]'."""
    if val is None:
        return None
    if isinstance(val, int):
        return json.dumps([f"CWE-{val}"])
    if isinstance(val, list):
        return json.dumps([str(v) for v in val if v])
    if isinstance(val, str) and val.startswith("["):
        return val  # already JSON array
    parts = [v.strip() for v in val.split(",") if v.strip()]
    return json.dumps(parts) if parts else None


# ---------------------------------------------------------------------------
# SQLiteStore
# ---------------------------------------------------------------------------


class SQLiteStore:
    """Structured findings store backed by SQLite.

    Database path::

        <base_path>/projects/<project_name>/sqlite/findings.db
    """

    def __init__(self, base_path: str | Path, project_name: str) -> None:
        self._db_path = (
            Path(base_path) / "projects" / project_name / "sqlite" / "findings.db"
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    args       TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS run_tools (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id         INTEGER,
                    tool           TEXT,
                    findings_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS run_repos (
                    id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    repo   TEXT
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint      TEXT UNIQUE,
                    run_id           INTEGER,
                    tool             TEXT,
                    domain           TEXT,
                    segment          TEXT,
                    repo             TEXT,
                    finding_type     TEXT,
                    severity         TEXT,
                    confidence       TEXT,
                    file             TEXT,
                    rule_id          TEXT,
                    url              TEXT,
                    host             TEXT,
                    port             TEXT,
                    vulnerability_id TEXT,
                    package_name     TEXT,
                    ecosystem        TEXT,
                    description      TEXT,
                    package_version  TEXT,
                    cwe              TEXT,
                    enriched         INTEGER DEFAULT 0,
                    meta             TEXT DEFAULT '{}',
                    first_seen       TEXT,
                    last_seen        TEXT,
                    seen_count       INTEGER,
                    status           TEXT,
                    triaged_at       TEXT,
                    triaged_by       TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_findings_tool
                    ON findings (tool);
                CREATE INDEX IF NOT EXISTS idx_findings_severity
                    ON findings (severity);
                CREATE INDEX IF NOT EXISTS idx_findings_fingerprint
                    ON findings (fingerprint);
                CREATE INDEX IF NOT EXISTS idx_findings_segment
                    ON findings (segment);
                CREATE INDEX IF NOT EXISTS idx_findings_repo
                    ON findings (repo);

                CREATE TABLE IF NOT EXISTS tool_audit_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name   TEXT    NOT NULL,
                    arguments   TEXT,
                    success     INTEGER NOT NULL DEFAULT 1,
                    error       TEXT,
                    duration_ms INTEGER,
                    called_at   TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_batches (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id       INTEGER,
                    finding_ids  JSON NOT NULL,
                    batch_data   JSON NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending',
                    run_attempts INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    started_at   TEXT,
                    completed_at TEXT
                );
            """)

    # ------------------------------------------------------------------
    # Run management
    # ------------------------------------------------------------------

    def create_run(self, args: dict) -> int:
        """Insert a new run record. Returns the run_id (int)."""
        from datetime import UTC, datetime

        created_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (args, created_at) VALUES (?, ?)",
                (json.dumps(args), created_at),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def add_run_tools(self, run_id: int, tools: list[dict]) -> None:
        """Insert one row per tool for a run."""
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO run_tools (run_id, tool, findings_count) VALUES (?, ?, ?)",
                [
                    (run_id, t.get("tool", ""), t.get("findings_count", 0))
                    for t in tools
                ],
            )

    def add_run_repos(self, run_id: int, repos: list[str]) -> None:
        """Insert one row per repo for a run."""
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO run_repos (run_id, repo) VALUES (?, ?)",
                [(run_id, repo) for repo in repos],
            )

    # ------------------------------------------------------------------
    # Findings management
    # ------------------------------------------------------------------

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
            fingerprint = _compute_fingerprint(finding)
            named: dict[str, Any] = {}
            meta: dict[str, Any] = {}

            # --- Pre-extract finding_type ---
            named["finding_type"] = _normalise_finding_type(finding.get("finding_type"))

            # --- Pre-extract cwe (any of the three source keys) ---
            raw_cwe = (
                finding.get("cwe") or finding.get("cwe_id") or finding.get("cwe_ids")
            )
            if raw_cwe is not None:
                named["cwe"] = _normalise_cwe(raw_cwe)

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
        with self._connect() as conn:
            conn.executemany(sql, rows_with_ts)

    def delete_findings(self, tools: list[str] | None = None) -> None:
        """Delete findings from the store.

        ``tools=None``   — DELETE all rows from findings, run_tools, run_repos,
                           and runs.
        ``tools=[...]``  — DELETE FROM findings WHERE tool IN (...).
                           Does NOT delete run / run_tools / run_repos rows.
        """
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def create_triage_batches(
        self, run_id: int, tool: str, repo: str, segment: str
    ) -> int:
        """Fetch active findings, compute batches, and persist to triage_batches.

        Returns the number of batches written.
        """
        from tally_mcp.batching import compute_batches

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
        else:
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
                    json_extract(meta, '$.risk_type'),
                    CAST(json_extract(meta, '$.line_start') AS INTEGER)
            """
        with self._connect() as conn:
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
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO triage_batches"
                " (run_id, finding_ids, batch_data, status, run_attempts)"
                " VALUES (?, ?, ?, ?, ?)",
                insert_rows,
            )
        return len(batches)

    def claim_triage_batch(self, run_id: int) -> dict | None:
        """Atomically claims the next pending batch for *run_id*.

        Returns the batch row as a dict (with JSON columns parsed) or None
        if no claimable batch exists.
        """
        with self._connect() as conn:
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

    def complete_triage_batch(self, batch_id: int, status: str) -> None:
        """Sets status and completed_at on the given batch."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE triage_batches
                SET status = ?, completed_at = datetime('now')
                WHERE id = ?
                """,
                (status, batch_id),
            )

    def reset_stale_triage_batches(self, run_id: int) -> int:
        """Reset in_progress batches for run_id back to pending.

        Returns the number of batches reset.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE triage_batches"
                " SET status = 'pending', started_at = NULL"
                " WHERE status = 'in_progress' AND run_id = ?",
                (run_id,),
            )
            return cur.rowcount

    # todo: The size of this method is out of control. break it on down
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
        conditions: list[tuple[str, str, list[str]]] = filters.get("conditions", [])
        page: int = filters.get("page", 1)
        page_size: int = filters.get("page_size", 200)
        offset = (page - 1) * page_size

        where_parts: list[str] = []
        params: list[Any] = []

        for col_expr, op, values in conditions:
            if not values:
                continue
            if col_expr == "finding_type":
                # finding_type is stored as a JSON array; use json_each().
                if op == "=":
                    # OR semantics: row matches if any element equals any value.
                    if len(values) == 1:
                        where_parts.append(
                            "EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                            " WHERE json_each.value = ?)"
                        )
                        params.append(values[0])
                    else:
                        phs = ",".join("?" * len(values))
                        where_parts.append(
                            f"EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                            f" WHERE json_each.value IN ({phs}))"
                        )
                        params.extend(values)
                elif op == "~=":
                    # OR semantics: row matches if any element contains any substring.
                    like_clauses = " OR ".join("json_each.value LIKE ?" for _ in values)
                    where_parts.append(
                        f"EXISTS (SELECT 1 FROM json_each(findings.finding_type)"
                        f" WHERE {like_clauses})"
                    )
                    params.extend(f"%{v}%" for v in values)
            elif op == "=":
                if len(values) == 1:
                    where_parts.append(f"{col_expr} = ?")
                    params.append(values[0])
                else:
                    placeholders = ",".join("?" * len(values))
                    where_parts.append(f"{col_expr} IN ({placeholders})")
                    params.extend(values)
            elif op == "~=":
                like_parts = [f"{col_expr} LIKE ?"] * len(values)
                where_parts.append(f"({'  OR  '.join(like_parts)})")
                params.extend(f"%{v}%" for v in values)

        sql = """
            SELECT fingerprint, run_id,
                   tool, domain, segment, repo,
                   finding_type, severity, confidence,
                   file, rule_id, url, host, port,
                   vulnerability_id, package_name, ecosystem,
                   description, package_version, cwe, enriched, meta
            FROM findings
        """
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        sql += " LIMIT ? OFFSET ?"
        params.extend([page_size, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        results: list[dict] = []
        for row in rows:
            metadata: dict[str, Any] = {}

            # 1. Seed with meta blob (lowest priority)
            try:
                meta_dict: dict[str, Any] = json.loads(row["meta"] or "{}")
                metadata.update(meta_dict)
            except (json.JSONDecodeError, TypeError):
                pass

            # 2. Named columns override meta (higher priority)
            for col in _DIRECT_COLUMNS:
                val = row[col]
                if val is not None:
                    metadata[col] = val

            # Renamed + aliased columns: expose under BOTH the SQLite name
            # and the ChromaDB-compatible name so --fields works with either.
            file_val = row["file"]
            if file_val is not None:
                metadata["file"] = file_val
                metadata["file_path"] = file_val

            host_val = row["host"]
            if host_val is not None:
                metadata["host"] = host_val
                metadata["ip_address"] = host_val

            fp_val = row["fingerprint"]
            if fp_val is not None:
                metadata["fingerprint"] = fp_val

            rid_val = row["run_id"]
            if rid_val is not None:
                metadata["run_id"] = rid_val

            # finding_type: stored as JSON array, return as list.
            ft_val = row["finding_type"]
            if ft_val:
                try:
                    metadata["finding_type"] = json.loads(ft_val)
                except json.JSONDecodeError:
                    metadata["finding_type"] = ft_val

            # cwe: stored as JSON array, return as list.
            cwe_val = row["cwe"]
            if cwe_val:
                try:
                    metadata["cwe"] = json.loads(cwe_val)
                except json.JSONDecodeError:
                    metadata["cwe"] = cwe_val

            metadata["enriched"] = bool(row["enriched"])

            results.append({"metadata": metadata, "distance": None, "document": ""})

        return results

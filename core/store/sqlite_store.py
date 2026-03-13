"""SQLite structured findings store for tally security findings."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from core.tools.constants import FINDING_TYPES, SEVERITY_LEVELS, TOOL_DOMAIN_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column mappings
# ---------------------------------------------------------------------------

# ChromaDB field name → SQLite named column name
_CHROMA_TO_SQLITE: dict[str, str] = {
    "tool": "tool",
    "domain": "domain",
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
}

# Named column names that are identical in ChromaDB and SQLite
_DIRECT_COLUMNS: tuple[str, ...] = (
    "tool",
    "domain",
    "finding_type",
    "severity",
    "confidence",
    "rule_id",
    "url",
    "port",
    "vulnerability_id",
    "package_name",
    "ecosystem",
)

# Comma-joined string fields in ChromaDB → stored as JSON arrays in meta
_COMMA_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "technology",
        "subcategory",
        "references",
        "aliases",
        "cwe_ids",
        "tags",
    }
)

# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _compute_fingerprint(finding: dict[str, Any]) -> str:
    """Compute a stable sha256 fingerprint from per-tool key fields."""
    tool = finding.get("tool", "")

    if tool == "gitleaks":
        key = "|".join(
            [
                tool,
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_number", "")),
            ]
        )
    elif tool == "semgrep":
        key = "|".join(
            [
                tool,
                str(finding.get("rule_id", "")),
                str(finding.get("file_path", "")),
                str(finding.get("line_start", "")),
            ]
        )
    elif tool == "nmap":
        key = "|".join(
            [
                tool,
                str(finding.get("ip_address", "")),
                str(finding.get("port", "")),
                str(finding.get("transport", "")),
            ]
        )
    elif tool in ("pip-audit", "npm-audit", "osv-scanner", "composer-audit"):
        key = "|".join(
            [
                tool,
                str(finding.get("package_name", "")),
                str(finding.get("vulnerability_id", "")),
                str(finding.get("ecosystem", "")),
            ]
        )
    elif tool == "zap":
        key = "|".join(
            [
                tool,
                str(finding.get("url", "")),
                str(finding.get("method", "")),
                str(finding.get("alert_name", "")),
            ]
        )
    else:
        safe = {
            k: v for k, v in sorted(finding.items()) if isinstance(v, (str, int, float))
        }
        key = json.dumps(safe, sort_keys=True)

    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Search parser
# ---------------------------------------------------------------------------

# Flag name → SQLite column name
_FLAG_TO_COLUMN: dict[str, str] = {
    "tool": "tool",
    "domain": "domain",
    "type": "finding_type",
    "severity": "severity",
    "confidence": "confidence",
    "file": "file",
    "rule": "rule_id",
    "url": "url",
    "host": "host",
    "port": "port",
    "vulnerability_id": "vulnerability_id",
    "package_name": "package_name",
    "ecosystem": "ecosystem",
}

# Meta flags and their actual JSON path field names
_META_FLAG_FIELDS: dict[str, str] = {
    "risk_type": "risk_type",
    "profile": "profile",
    "param": "param",
    "alert": "alert_name",
    "method": "method",
    "service": "service",
    "transport": "transport",
}


class SearchValidationError(Exception):
    """User-facing validation error for SQLite search parsing."""


def parse_sqlite_search_command(
    args: list[str], known_tools: frozenset[str]
) -> dict[str, Any]:
    """Parse --flag=value search args into a structured filter dict.

    Returns::

        {
            "conditions": [(col_expr, op, values_list), ...],
            "page": 1,
            "page_size": 200,
        }

    Where ``col_expr`` is a SQLite column name or ``json_extract(meta, '$.field')``.
    ``op`` is ``"="`` or ``"~="``.  ``values_list`` is a non-empty list of strings.
    """
    conditions: list[tuple[str, str, list[str]]] = []
    page: int = 1
    page_size: int = 200

    for arg in args:
        if not arg.startswith("--"):
            if "~=" in arg or "=" in arg:
                raise SearchValidationError(
                    f"Old syntax detected: '{arg}'\n"
                    "Use --flag=value syntax. "
                    "Run 'search --help' for examples."
                )
            raise SearchValidationError(
                f"Unexpected argument: '{arg}'\n"
                "All search arguments use --flag=value syntax. "
                "Run 'search --help' for examples."
            )

        rest = arg[2:]  # strip "--"

        if "~=" in rest:
            flag, _, val = rest.partition("~=")
            col_expr = _resolve_col_expr(flag)
            values = [v.strip() for v in val.split(",") if v.strip()]
            if values:
                conditions.append((col_expr, "~=", values))
            continue

        if "=" not in rest:
            raise SearchValidationError(
                f"Flag '{arg}' requires a value, e.g. {arg}=<value>."
            )

        flag, _, val = rest.partition("=")

        if flag == "page-size":
            try:
                page_size = int(val)
                if page_size < 1:
                    raise ValueError
            except ValueError:
                raise SearchValidationError("--page-size must be a positive integer.")
        elif flag == "page":
            try:
                page = int(val)
                if page < 1:
                    raise ValueError
            except ValueError:
                raise SearchValidationError("--page must be a positive integer.")
        elif flag == "help":
            pass  # handled upstream in cmd_search
        else:
            col_expr = _resolve_col_expr(flag)
            values = [v.strip() for v in val.split(",") if v.strip()]
            _validate_flag_values(flag, values, known_tools)
            if values:
                conditions.append((col_expr, "=", values))

    return {"conditions": conditions, "page": page, "page_size": page_size}


def _resolve_col_expr(flag: str) -> str:
    """Return the SQLite column expression for a flag name."""
    if flag in _META_FLAG_FIELDS:
        field = _META_FLAG_FIELDS[flag]
        return f"json_extract(meta, '$.{field}')"
    if flag in _FLAG_TO_COLUMN:
        return _FLAG_TO_COLUMN[flag]
    raise SearchValidationError(
        f"Unknown filter flag '--{flag}'. Run 'search --help' for valid flags."
    )


def _validate_flag_values(
    flag: str, values: list[str], known_tools: frozenset[str]
) -> None:
    """Validate controlled-vocabulary flags. Raises SearchValidationError."""
    if flag == "tool":
        for v in values:
            if v not in known_tools:
                raise SearchValidationError(
                    f"Tool {v!r} not found. Run 'tools' to see configured tools."
                )
    elif flag == "domain":
        domain_values = set(TOOL_DOMAIN_MAP.values())
        for v in values:
            if v not in domain_values:
                raise SearchValidationError(
                    f"Unknown domain {v!r}. "
                    f"Valid domains: {', '.join(sorted(domain_values))}"
                )
    elif flag == "type":
        for v in values:
            if v not in FINDING_TYPES:
                raise SearchValidationError(
                    f"Unknown type {v!r}. "
                    f"Valid types: {', '.join(sorted(FINDING_TYPES))}"
                )
    elif flag == "severity":
        for v in values:
            if v not in SEVERITY_LEVELS:
                raise SearchValidationError(
                    f"Unknown severity {v!r}. "
                    f"Valid severities: {', '.join(sorted(SEVERITY_LEVELS))}"
                )


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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
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
                    enriched         INTEGER DEFAULT 0,
                    meta             TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_findings_tool
                    ON findings (tool);
                CREATE INDEX IF NOT EXISTS idx_findings_severity
                    ON findings (severity);
                CREATE INDEX IF NOT EXISTS idx_findings_fingerprint
                    ON findings (fingerprint);
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

        rows: list[tuple] = []
        for finding in findings:
            fingerprint = _compute_fingerprint(finding)
            named: dict[str, Any] = {}
            meta: dict[str, Any] = {}

            for key, val in finding.items():
                col = _CHROMA_TO_SQLITE.get(key)
                if col is not None:
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
                    1,  # enriched
                    json.dumps(meta),
                )
            )

        sql = """
            INSERT INTO findings (
                fingerprint, run_id, tool, domain, finding_type, severity,
                confidence, file, rule_id, url, host, port,
                vulnerability_id, package_name, ecosystem, enriched, meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (fingerprint) DO UPDATE SET
                run_id     = excluded.run_id,
                severity   = excluded.severity,
                confidence = excluded.confidence,
                enriched   = excluded.enriched,
                meta       = excluded.meta
        """
        with self._connect() as conn:
            conn.executemany(sql, rows)

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
            if op == "=":
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
            SELECT tool, domain, finding_type, severity, confidence,
                   file, rule_id, url, host, port,
                   vulnerability_id, package_name, ecosystem, enriched, meta
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

            # Direct-name columns (same in ChromaDB and SQLite)
            for col in _DIRECT_COLUMNS:
                val = row[col]
                if val is not None:
                    metadata[col] = val

            # Renamed columns
            file_val = row["file"]
            if file_val is not None:
                metadata["file_path"] = file_val
            host_val = row["host"]
            if host_val is not None:
                metadata["ip_address"] = host_val

            metadata["enriched"] = bool(row["enriched"])

            # Merge meta JSON blob
            try:
                meta_dict: dict[str, Any] = json.loads(row["meta"] or "{}")
                metadata.update(meta_dict)
            except (json.JSONDecodeError, TypeError):
                pass

            results.append({"metadata": metadata, "distance": None, "document": ""})

        return results

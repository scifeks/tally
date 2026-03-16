"""Finding-related MCP tools."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.store.sqlite_store import SQLiteStore

# Injected at startup by server.py
_store: SQLiteStore | None = None

from ..config import BATCH_TIMEOUT_SECONDS, MAX_BATCH_SIZE  # noqa: E402
from .project import get_project_config  # noqa: E402


def _extract_line(meta: dict) -> int:
    return meta.get("line_start") or meta.get("line_number") or 0


def _parse_row(row: dict) -> dict:
    """JSON-parse meta, finding_type, and cwe columns in-place."""
    if isinstance(row.get("meta"), str):
        row["meta"] = json.loads(row["meta"])
    if isinstance(row.get("finding_type"), str):
        row["finding_type"] = json.loads(row["finding_type"])
    if isinstance(row.get("cwe"), str):
        row["cwe"] = json.loads(row["cwe"])
    return row


def _write_audit(
    tool_name: str,
    arguments: dict,
    success: bool,
    error: str | None,
    duration_ms: int,
) -> None:
    """Write an audit row directly (used by timeout catch block)."""
    assert _store is not None
    called_at = datetime.now(UTC).isoformat()
    with _store._connect() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO tool_audit_log "
            "(tool_name, arguments, success, error, duration_ms, called_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                tool_name,
                json.dumps(arguments),
                1 if success else 0,
                error,
                duration_ms,
                called_at,
            ),
        )


async def get_finding(finding_id: int) -> dict:
    """Retrieve a single finding by its primary-key ID.

    Args:
        finding_id: The integer primary key of the finding row.

    Returns:
        A dict representation of the finding row with JSON columns parsed.

    Raises:
        ValueError: If no finding with the given ID exists.
    """
    assert _store is not None
    row = await asyncio.to_thread(_store.get_finding, finding_id)
    if row is None:
        raise ValueError(f"Finding {finding_id} not found")
    return _parse_row(row)


async def get_findings_batch(
    project: str,
    repo: str | None = None,
    tools: list[str] | None = None,
    domain: str | None = None,
    status: str | None = None,
    max_results: int | None = None,
) -> list[dict]:
    """Retrieve a filtered batch of findings for triage.

    Args:
        project: Project name to query findings for.
        repo: Optional repository filter — resolved via project config.
        tools: Optional list of tool names to restrict results to.
        domain: Optional domain filter (e.g. ``"sast"``, ``"secrets"``).
        status: Optional status filter (e.g. ``"open"``, ``"fixed"``).
        max_results: Optional cap; clamped to MAX_BATCH_SIZE.

    Returns:
        A list of finding dicts sorted by (file, line). Returns ``[]`` on
        timeout without raising.
    """
    assert _store is not None
    limit = min(max_results, MAX_BATCH_SIZE) if max_results else MAX_BATCH_SIZE
    file_prefix: str | None = None
    if repo:
        cfg = await get_project_config(project)
        repos = {r["name"]: r["path"] for r in cfg.get("repositories", [])}
        if repo not in repos:
            raise ValueError(f"Repo '{repo}' not in project config")
        file_prefix = repos[repo]

    call_args: dict = {
        "project": project,
        "repo": repo,
        "tools": tools,
        "domain": domain,
        "status": status,
        "max_results": max_results,
    }
    start = datetime.now(UTC)
    try:
        rows = await asyncio.wait_for(
            asyncio.to_thread(
                _store.get_findings, tools, domain, status, file_prefix, limit
            ),
            timeout=BATCH_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        _write_audit("get_findings_batch", call_args, False, "timeout", duration_ms)
        return []

    rows = [_parse_row(r) for r in rows]
    rows.sort(key=lambda r: (r.get("file") or "", _extract_line(r.get("meta") or {})))
    return rows


# ---------------------------------------------------------------------------
# Phase 3 stubs (kept async so _run_with_audit can always await)
# ---------------------------------------------------------------------------


async def update_finding(  # type: ignore[return]
    finding_id: int,
    confidence: str | None = None,
    finding_type: str | None = None,
    severity: str | None = None,
    reasoning: str | None = None,
    remediation: str | None = None,
    attack_vector: str | None = None,
    call_stack: str | None = None,
) -> bool:
    """Update enrichment fields on a single finding."""
    raise NotImplementedError("not implemented")


async def update_findings_batch(updates: list[dict]) -> dict:  # type: ignore[return]
    """Apply updates to multiple findings in a single call."""
    raise NotImplementedError("not implemented")

"""Finding-related MCP tools."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from core.store.sqlite_store import SQLiteStore

# Injected at startup by server.py
_store: SQLiteStore | None = None
_project_name: str | None = None

from core.tools.constants import (  # noqa: E402
    CONFIDENCE_LEVELS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
)

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


def _reconstruct_abs_path(
    file: str | None, repo_name: str | None, repos: list[dict]
) -> str | None:
    """Reconstruct absolute path from relative file + repo name."""
    if not file or not repo_name:
        return None
    for r in repos:
        if r["name"] == repo_name:
            return r["path"].rstrip("/") + file
    return None


def _resolve_repo_path(repo_name: str | None, repos: list[dict]) -> str | None:
    """Return the base directory path for *repo_name*, or None."""
    if not repo_name:
        return None
    for r in repos:
        if r["name"] == repo_name:
            return r["path"]
    return None


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
    row = _parse_row(row)
    repos: list[dict] = []
    if _project_name:
        try:
            cfg = await get_project_config(_project_name)
            repos = cfg.get("repositories", [])
        except FileNotFoundError:
            pass
    row["abs_path"] = _reconstruct_abs_path(row.get("file"), row.get("repo"), repos)
    row["repo_path"] = _resolve_repo_path(row.get("repo"), repos)
    return row


async def get_findings_batch(finding_ids: list[int]) -> list[dict]:
    """Return enriched finding data for the given IDs."""
    return [
        finding
        for fid in finding_ids
        if (finding := await get_finding(fid)) is not None
    ]


async def complete_triage_batch(
    batch_id: int, status: Literal["success", "failed"]
) -> None:
    """Sets status and completed_at on the given batch."""
    assert _store is not None
    await asyncio.to_thread(_store.complete_triage_batch, batch_id, status)


async def update_finding(
    finding_id: int,
    confidence: str | None = None,
    finding_type: str | None = None,
    severity: str | None = None,
    reasoning: str | None = None,
    remediation: str | None = None,
    attack_vector: str | None = None,
    call_stack: str | None = None,
    strategy: str = "",
) -> bool:
    """Update enrichment fields on a single finding."""
    assert _store is not None
    start = datetime.now(UTC)
    call_args: dict = {
        "finding_id": finding_id,
        "confidence": confidence,
        "finding_type": finding_type,
        "severity": severity,
        "reasoning": reasoning,
        "remediation": remediation,
        "attack_vector": attack_vector,
        "call_stack": call_stack,
        "strategy": strategy,
    }

    def _fail(err: str) -> None:
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        _write_audit("update_finding", call_args, False, err, duration_ms)

    # todo: this repeating error raising is dumb
    # Validate required fields not None
    if confidence is None:
        err = "Missing required field: confidence"
        _fail(err)
        raise ValueError(err)
    if finding_type is None:
        err = "Missing required field: finding_type"
        _fail(err)
        raise ValueError(err)
    if severity is None:
        err = "Missing required field: severity"
        _fail(err)
        raise ValueError(err)
    if reasoning is None:
        err = "Missing required field: reasoning"
        _fail(err)
        raise ValueError(err)
    if remediation is None:
        err = "Missing required field: remediation"
        _fail(err)
        raise ValueError(err)

    # Validate enum values
    if confidence not in CONFIDENCE_LEVELS:
        err = f"Invalid confidence: '{confidence}'. Must be one of: {CONFIDENCE_LEVELS}"
        _fail(err)
        raise ValueError(err)
    if finding_type not in FINDING_TYPES:
        err = f"Invalid finding_type: '{finding_type}'. Must be one of: {FINDING_TYPES}"
        _fail(err)
        raise ValueError(err)
    if severity not in SEVERITY_LEVELS:
        err = f"Invalid severity: '{severity}'. Must be one of: {SEVERITY_LEVELS}"
        _fail(err)
        raise ValueError(err)

    def _do_update() -> bool:
        assert _store is not None
        row = _store.get_finding(finding_id)
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
        with _store._connect() as conn:  # noqa: SLF001
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

    try:
        result = await asyncio.to_thread(_do_update)
    except Exception as exc:
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        _write_audit("update_finding", call_args, False, str(exc), duration_ms)
        raise

    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    _write_audit("update_finding", call_args, True, None, duration_ms)
    return result


async def update_findings_batch(updates: list[dict]) -> dict:
    """Apply updates to multiple findings in a single call."""
    results: dict = {}
    for i, payload in enumerate(updates):
        try:
            finding_id = payload["finding_id"]
            await update_finding(**payload)
            results[str(finding_id)] = {"finding_id": finding_id, "status": "updated"}
        except Exception as exc:
            key = payload.get("finding_id", i)
            results[str(key)] = {
                "finding_id": key,
                "status": "error",
                "error": str(exc),
            }
    return results

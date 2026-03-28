"""Finding-related MCP tools."""

from __future__ import annotations

import asyncio
import json

from application.findings.updater import (
    FindingUpdateService,
    reconstruct_abs_path,
    resolve_repo_path,
)
from tally_mcp.context import FindingsContext

# Injected at startup by server.py
_ctx: FindingsContext | None = None
_service: FindingUpdateService | None = None


def init(ctx: FindingsContext) -> None:
    """Inject repository dependencies. Called once at server startup."""
    global _ctx, _service
    _ctx = ctx
    _service = FindingUpdateService(ctx.finding_repo, ctx.audit_repo)


def _parse_row(row: dict) -> dict:
    """JSON-parse meta, finding_type, and cwe columns in-place."""
    if isinstance(row.get("meta"), str):
        row["meta"] = json.loads(row["meta"])
    if isinstance(row.get("finding_type"), str):
        row["finding_type"] = json.loads(row["finding_type"])
    if isinstance(row.get("cwe"), str):
        row["cwe"] = json.loads(row["cwe"])
    return row


async def get_finding(finding_id: int) -> dict:
    """Retrieve a single finding by its primary-key ID.

    Args:
        finding_id: The integer primary key of the finding row.

    Returns:
        A dict representation of the finding row with JSON columns parsed.

    Raises:
        ValueError: If no finding with the given ID exists.
    """
    assert _ctx is not None
    row = await asyncio.to_thread(_ctx.finding_repo.get_finding, finding_id)
    if row is None:
        raise ValueError(f"Finding {finding_id} not found")
    row = _parse_row(row)
    repos: list[dict] = []
    if _ctx.project_name:
        try:
            from tally_mcp.tools.project import get_project_config

            cfg = await get_project_config(_ctx.project_name)
            repos = cfg.get("repositories", [])
        except FileNotFoundError:
            pass
    row["abs_path"] = reconstruct_abs_path(row.get("file"), row.get("repo"), repos)
    row["repo_path"] = resolve_repo_path(row.get("repo"), repos)
    return row


async def get_findings_batch(finding_ids: list[int]) -> list[dict]:
    """Return enriched finding data for the given IDs."""
    return [
        finding
        for fid in finding_ids
        if (finding := await get_finding(fid)) is not None
    ]


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
    assert _service is not None
    return await _service.update(
        finding_id,
        confidence,
        finding_type,
        severity,
        reasoning,
        remediation,
        attack_vector,
        call_stack,
        strategy,
    )


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

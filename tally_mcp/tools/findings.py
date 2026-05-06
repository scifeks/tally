"""Finding-related MCP tools."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from application.findings.updater import FindingUpdateService
from tally_mcp.context import FindingsContext

if TYPE_CHECKING:
    from core.config.manager import ConfigManager

# Injected at startup by server.py
_ctx: FindingsContext | None = None
_service: FindingUpdateService | None = None
_DEFAULT_TRIAGED_BY = "claudecode"


def init(ctx: FindingsContext, config_manager: ConfigManager | None = None) -> None:
    """Inject repository dependencies. Called once at server startup."""
    global _ctx, _service
    _ctx = ctx
    _service = FindingUpdateService(
        ctx.finding_repo,
        ctx.audit_repo,
        config_manager=config_manager,
        triaged_by=os.environ.get("TALLY_TRIAGED_BY", _DEFAULT_TRIAGED_BY),
    )


async def get_finding(finding_id: int) -> dict:
    """Retrieve a single finding by its primary-key ID.

    Args:
        finding_id: The integer primary key of the finding row.

    Returns:
        A dict representation of the finding with JSON columns parsed and
        ``abs_path`` / ``repo_path`` resolved against the project's repos.

    Raises:
        ValueError: If no finding with the given ID exists.
    """
    assert _ctx is not None
    finding = await asyncio.to_thread(_ctx.finding_repo.get_finding, finding_id)
    if finding is None:
        raise ValueError(f"Finding {finding_id} not found")
    row: dict = asdict(finding)
    assert _service is not None
    abs_path, repo_path = _service.resolve_finding_paths(
        row.get("file"), row.get("repo"), _ctx.project_name
    )
    row["abs_path"] = abs_path
    row["repo_path"] = repo_path
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

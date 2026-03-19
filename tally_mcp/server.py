"""MCP server entry point for Tally triage agent.

Run as:
    python -m tally_mcp.server --project <name>
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.config.manager import ConfigManager
from core.store import make_store

from .context import FindingsContext
from .tools import findings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
_parser = argparse.ArgumentParser(description="Tally MCP server")
_parser.add_argument("--project", required=True, help="Project name")
_args = _parser.parse_args()

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------
_app_root = Path(__file__).parent.parent
_project_name: str = _args.project
_cfg = ConfigManager(str(_app_root)).global_config  # noqa: F841 — reserved for Phase 2
_run_repo, _finding_repo, _triage_repo, _audit_repo = make_store(
    _app_root, _project_name
)
findings.init(
    FindingsContext(
        finding_repo=_finding_repo,
        audit_repo=_audit_repo,
        triage_repo=_triage_repo,
        project_name=_project_name,
    )
)

logger.info("Tally MCP server starting — project=%s", _project_name)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------
mcp = FastMCP("tally")


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def _audit(
    tool_name: str,
    arguments: dict,
    success: bool,
    error: str | None,
    duration_ms: int,
) -> None:
    """Insert one row into tool_audit_log (synchronous)."""
    _audit_repo.log_event(tool_name, arguments, success, error, duration_ms)


async def _run_with_audit(tool_name: str, arguments: dict, fn, *args, **kwargs):
    """Call *fn* and write an audit row regardless of success/failure."""
    start = datetime.now(UTC)
    error: str | None = None
    result = None
    try:
        result = await fn(*args, **kwargs)
    except NotImplementedError:
        error = "not implemented"
        raise
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        await asyncio.to_thread(
            _audit,
            tool_name,
            arguments,
            error is None,
            error,
            duration_ms,
        )
    return result


# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_findings_batch(finding_ids: list[int]) -> list[dict]:
    """Return enriched data for the specified finding IDs."""
    return await _run_with_audit(
        "get_findings_batch",
        {"finding_ids": finding_ids},
        findings.get_findings_batch,
        finding_ids,
    )


@mcp.tool()
async def update_findings_batch(updates: list[dict]) -> dict:
    """Apply updates to multiple findings in a single call."""
    return await _run_with_audit(
        "update_findings_batch",
        {"updates": updates},
        findings.update_findings_batch,
        updates,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")

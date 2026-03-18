"""MCP server entry point for Tally triage agent.

Run as:
    python -m tally_mcp.server --project <name>
"""

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.config.manager import ConfigManager
from core.store.sqlite_store import SQLiteStore

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
_store = SQLiteStore(_app_root, _project_name)
findings._store = _store
findings._project_name = _project_name

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
    called_at = datetime.now(UTC).isoformat()
    with _store._connect() as conn:  # noqa: SLF001
        conn.execute(
            """
            INSERT INTO tool_audit_log
                (tool_name, arguments, success, error, duration_ms, called_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tool_name,
                json.dumps(arguments),
                1 if success else 0,
                error,
                duration_ms,
                called_at,
            ),
        )


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
async def get_findings_batch(run_id: int) -> dict | None:
    """Atomically claims and returns the next pending batch for the given run."""
    return await _run_with_audit(
        "get_findings_batch",
        {"run_id": run_id},
        findings.get_findings_batch,
        run_id,
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

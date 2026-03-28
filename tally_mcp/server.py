"""MCP server entry point for Tally triage agent.

Run as:
    python -m tally_mcp.server --project <name>
"""

import argparse
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from application.audit.runner import AuditRunner
from infrastructure.store import make_store

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
_audit_runner = AuditRunner(_audit_repo)

logger.info("Tally MCP server starting — project=%s", _project_name)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------
mcp = FastMCP("tally")


# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_findings_batch(finding_ids: list[int]) -> list[dict]:
    """Return enriched data for the specified finding IDs."""
    return await _audit_runner.run(
        "get_findings_batch",
        {"finding_ids": finding_ids},
        findings.get_findings_batch,
        finding_ids,
    )


@mcp.tool()
async def update_findings_batch(updates: list[dict]) -> dict:
    """Apply updates to multiple findings in a single call."""
    return await _audit_runner.run(
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

"""MCP triage orchestrator — drives AI triage sessions for security findings."""

import json
import logging
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from mcp.config import SESSION_TIMEOUT_SECONDS
from mcp.prompts import api_trace as _api_trace
from mcp.prompts import code_trace as _code_trace
from mcp.prompts import dependency as _dependency
from mcp.prompts import enrich_only as _enrich_only

_log = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).parent.parent

TOOL_STRATEGY: dict[str, str] = {
    "semgrep": "code_trace",
    "zap": "api_trace",
    "osv-scanner": "dependency",
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "composer-audit": "dependency",
    "gitleaks": "enrich_only",
    "nmap": "skip",
    "tree-sitter": "skip",
}

STRATEGY_PROMPT: dict[str, object] = {
    "code_trace": _code_trace.render,
    "api_trace": _api_trace.render,
    "dependency": _dependency.render,
    "enrich_only": _enrich_only.render,
}


def _db_path(project: str) -> Path:
    return _APP_ROOT / "projects" / project / "sqlite" / "findings.db"


def _write_mcp_json(project: str) -> Path:
    mcp_json_path = _APP_ROOT / ".mcp.json"
    payload = {
        "mcpServers": {
            "tally-mcp": {
                "type": "stdio",
                "command": "python3",
                "args": [
                    "mcp/server.py",
                    "--project",
                    project,
                ],
            }
        }
    }
    mcp_json_path.write_text(json.dumps(payload, indent=2))
    return mcp_json_path


def run_triage(project: str) -> dict[str, int]:
    """Run AI triage sessions for untriaged findings.

    Returns a dict with keys: sessions_run, success, failed, incomplete.
    Raises FileNotFoundError if the project database does not exist.
    """
    db = _db_path(project)
    if not db.exists():
        raise FileNotFoundError(f"Project database not found: {db}")

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT id, tool FROM findings WHERE triaged_at IS NULL"
        ).fetchall()
    finally:
        conn.close()

    # Group by strategy
    strategy_batches: dict[str, list[int]] = {}
    skipped = 0
    for finding_id, tool in rows:
        strategy = TOOL_STRATEGY.get(tool or "", "enrich_only")
        if strategy == "skip":
            skipped += 1
            continue
        strategy_batches.setdefault(strategy, []).append(finding_id)

    if skipped:
        _log.info("Skipped %d findings with skip-strategy tools", skipped)

    mcp_json_path = _write_mcp_json(project)

    sessions_run = 0
    success = 0
    failed = 0
    incomplete = 0

    try:
        for strategy, finding_ids in strategy_batches.items():
            render_fn = STRATEGY_PROMPT[strategy]
            prompt_text = render_fn(finding_ids, project)  # type: ignore[operator]
            session_start = datetime.now(UTC).isoformat()
            sessions_run += 1

            try:
                result = subprocess.run(
                    [
                        "claude",
                        "--print",
                        "--dangerously-skip-permissions",
                        prompt_text,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=SESSION_TIMEOUT_SECONDS,
                    cwd=str(_APP_ROOT),
                )
            except subprocess.TimeoutExpired:
                _log.error(
                    "Triage session timed out after %ds (strategy=%s)",
                    SESSION_TIMEOUT_SECONDS,
                    strategy,
                )
                failed += 1
                continue
            except Exception as exc:
                _log.error(
                    "Subprocess error during triage (strategy=%s): %s", strategy, exc
                )
                failed += 1
                continue

            if result.returncode != 0:
                _log.error(
                    "Triage session failed (strategy=%s, rc=%d): %s",
                    strategy,
                    result.returncode,
                    result.stderr,
                )
                failed += 1
                continue

            # Check audit log for write activity in this session
            conn2 = sqlite3.connect(str(db))
            try:
                audit_rows = conn2.execute(
                    "SELECT COUNT(*) FROM tool_audit_log "
                    "WHERE tool_name IN ('update_finding', 'update_findings_batch') "
                    "AND called_at >= ?",
                    (session_start,),
                ).fetchone()
                updated_count = audit_rows[0] if audit_rows else 0
            finally:
                conn2.close()

            if updated_count > 0:
                _log.info(
                    "Triage session success (strategy=%s, updates=%d)",
                    strategy,
                    updated_count,
                )
                success += 1
            else:
                _log.warning(
                    "Session completed but no findings were updated — "
                    "possible prompt failure or empty batch (strategy=%s)",
                    strategy,
                )
                incomplete += 1
    finally:
        mcp_json_path.unlink(missing_ok=True)

    return {
        "sessions_run": sessions_run,
        "success": success,
        "failed": failed,
        "incomplete": incomplete,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    print(run_triage(args.project))

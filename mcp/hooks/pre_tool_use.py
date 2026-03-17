#!/usr/bin/env python3
"""Pre-tool-use hook: logs every Claude Code tool call to tool_audit_log."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_APP_ROOT = Path(__file__).parent.parent.parent


def _resolve_db(app_root: Path) -> Path | None:
    """Read .mcp.json → extract project name → return findings.db path."""
    mcp_json = app_root / ".mcp.json"
    if not mcp_json.exists():
        print(f"pre_tool_use: .mcp.json not found at {mcp_json}", file=sys.stderr)
        return None
    try:
        data = json.loads(mcp_json.read_text())
        args: list = data["mcpServers"]["tally-mcp"]["args"]
        project = args[args.index("--project") + 1]
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"pre_tool_use: malformed .mcp.json: {exc}", file=sys.stderr)
        return None
    return app_root / "projects" / project / "sqlite" / "findings.db"


def main(app_root: Path | None = None) -> int:
    root = app_root if app_root is not None else _DEFAULT_APP_ROOT
    try:
        payload = json.loads(sys.stdin.read())
        tool_name: str = payload["tool_name"]
        tool_input: dict = payload.get("tool_input", {})
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"pre_tool_use: malformed input: {exc}", file=sys.stderr)
        return 0
    db_path = _resolve_db(root)
    if db_path is None:
        return 0
    called_at = datetime.now(UTC).isoformat()
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO tool_audit_log"
                " (tool_name, arguments, success, called_at) VALUES (?, ?, 1, ?)",
                (tool_name, json.dumps(tool_input), called_at),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"pre_tool_use: DB write failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Claude-backed triage backend."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageBackendPort,
    TriageSessionResult,
)

_TRIAGED_BY = "claudecode"

# Keep these flags paired so noninteractive triage cannot gain shell,
# edit, or web access through the Claude process.
_DISALLOWED_TOOLS = "Bash,Write,Edit,MultiEdit,WebFetch,WebSearch"


class ClaudeTriageAgent(TriageBackendPort):
    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        mcp_json_path = app_root / ".mcp.json"
        payload = self._build_mcp_payload(
            project=project, run_id=run_id, app_root=app_root
        )
        mcp_json_path.write_text(json.dumps(payload, indent=2))
        try:
            yield PreparedTriageSession(cwd=app_root)
        finally:
            mcp_json_path.unlink(missing_ok=True)

    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult:
        try:
            completed = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--dangerously-skip-permissions",
                    "--disallowedTools",
                    _DISALLOWED_TOOLS,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(cwd),
            )
        except subprocess.TimeoutExpired:
            return TriageSessionResult(
                success=False,
                returncode=-1,
                stderr="",
                error=f"timed out after {timeout_seconds}s",
            )
        except Exception as exc:
            return TriageSessionResult(
                success=False,
                returncode=-1,
                stderr="",
                error=str(exc),
            )

        return TriageSessionResult(
            success=completed.returncode == 0,
            returncode=completed.returncode,
            stderr=completed.stderr or "",
        )

    def _build_mcp_payload(self, *, project: str, run_id: int, app_root: Path) -> dict:
        venv_python = app_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            raise RuntimeError(f"Venv Python not found at {venv_python}")
        return {
            "mcpServers": {
                "tally-mcp": {
                    "type": "stdio",
                    "command": str(venv_python),
                    "args": [
                        "-m",
                        "tally_mcp.server",
                        "--project",
                        project,
                    ],
                    "env": {
                        "TALLY_TRIAGE_RUN_ID": str(run_id),
                        "TALLY_TRIAGED_BY": _TRIAGED_BY,
                    },
                    "permissions": {
                        "allow": ["get_findings_batch", "update_findings_batch"],
                        "deny": ["*"],
                    },
                }
            }
        }

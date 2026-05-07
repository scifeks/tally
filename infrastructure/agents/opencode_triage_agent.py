"""OpenCode-backed triage backend."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageBackendPort,
    TriageSessionResult,
)

_MCP_SERVER_NAME = "tally-mcp"
_RUN_OUTPUT_FORMAT = "json"
_TRIAGED_BY = "opencode"


class OpenCodeTriageAgent(TriageBackendPort):
    """OpenCode-backed triage backend."""

    def __init__(self) -> None:
        self._session_env: dict[str, str] | None = None

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        with tempfile.TemporaryDirectory(
            prefix=".tally-opencode-", dir=app_root
        ) as temp_dir:
            session_dir = Path(temp_dir)
            config_path = session_dir / "opencode.json"
            payload = self._build_config_payload(
                project=project,
                run_id=run_id,
            )
            config_path.write_text(json.dumps(payload, indent=2))
            self._session_env = {"OPENCODE_CONFIG": str(config_path)}
            try:
                yield PreparedTriageSession(cwd=app_root)
            finally:
                self._session_env = None

    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult:
        try:
            completed = subprocess.run(
                self._build_run_command(cwd=cwd),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(cwd),
                env=self._build_session_env(),
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

        stderr = completed.stderr or ""
        if completed.stdout:
            stderr = f"{stderr}\n{completed.stdout}" if stderr else completed.stdout

        return TriageSessionResult(
            success=completed.returncode == 0,
            returncode=completed.returncode,
            stderr=stderr,
        )

    def _build_run_command(self, *, cwd: Path) -> list[str]:
        return [
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--dir",
            str(cwd),
            "--format",
            _RUN_OUTPUT_FORMAT,
        ]

    def _build_session_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self._session_env is not None:
            env.update(self._session_env)
        return env

    def _build_config_payload(
        self,
        *,
        project: str,
        run_id: int,
    ) -> dict:
        return {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                _MCP_SERVER_NAME: {
                    "type": "local",
                    "enabled": True,
                    "command": [
                        sys.executable,
                        "-m",
                        "tally_mcp.server",
                        "--project",
                        project,
                    ],
                    "environment": {
                        "TALLY_TRIAGE_RUN_ID": str(run_id),
                        "TALLY_TRIAGED_BY": _TRIAGED_BY,
                    },
                }
            },
            "permission": self._build_permission_payload(),
        }

    def _build_permission_payload(self) -> dict:
        # TODO(opencode-triage 1.5): replace `read: *: allow` with an
        # explicit deny list sourced from a user-configurable global-config
        # field. With --dangerously-skip-permissions in effect, only
        # explicit denies stop the read tool from accessing any path the
        # Tally process can see.
        return {
            "edit": "deny",
            "bash": {"*": "deny"},
            "webfetch": "deny",
            "tally-mcp_get_findings_batch": "allow",
            "tally-mcp_update_findings_batch": "allow",
            "tally-mcp_*": "deny",
            "read": {"*": "allow"},
            "write": {"*": "deny"},
        }

"""OpenCode-backed triage backend."""

from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageBackendPort,
    TriageSessionResult,
)

_MCP_SERVER_NAME = "tally-mcp"
_MCP_TOOL_PERMISSION_PATTERN = "tally-mcp_*"
_RUN_OUTPUT_FORMAT = "json"


class OpenCodeTriageAgent(TriageBackendPort):
    """OpenCode-backed triage backend.

    Phase 3.2 prepares disposable OpenCode config material locally and points
    the runtime at it via ``OPENCODE_CONFIG``. The actual ``opencode run``
    invocation remains blocked by B1/B3.
    """

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
                app_root=app_root,
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
        del prompt, timeout_seconds, cwd
        raise NotImplementedError(
            "OpenCode triage execution is not implemented yet. "
            "Phase 3.3 now prepares disposable config material plus a hardened "
            "permission profile, but final execution still depends on the "
            "remaining B1/B3 decisions."
        )

    def _build_run_command(self, *, cwd: Path) -> list[str]:
        return [
            "opencode",
            "run",
            "--dir",
            str(cwd),
            "--format",
            _RUN_OUTPUT_FORMAT,
        ]

    def _build_config_payload(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ) -> dict:
        venv_python = app_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            raise RuntimeError(f"Venv Python not found at {venv_python}")
        return {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                _MCP_SERVER_NAME: {
                    "type": "local",
                    "enabled": True,
                    "command": [
                        str(venv_python),
                        "-m",
                        "tally_mcp.server",
                        "--project",
                        project,
                    ],
                    "environment": {
                        "TALLY_TRIAGE_RUN_ID": str(run_id),
                    },
                }
            },
            "permission": self._build_permission_payload(),
        }

    def _build_permission_payload(self) -> dict:
        return {
            "edit": "deny",
            "bash": {"*": "deny"},
            "webfetch": "deny",
            _MCP_TOOL_PERMISSION_PATTERN: "allow",
            "rules": [
                {
                    "permission": "read",
                    "action": "allow",
                    "pattern": "**/*",
                },
                {
                    "permission": "write",
                    "action": "deny",
                    "pattern": "**/*",
                },
                {
                    "permission": "bash",
                    "action": "deny",
                    "pattern": "*",
                },
            ],
        }

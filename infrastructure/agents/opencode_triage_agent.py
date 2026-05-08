"""OpenCode-backed one-shot triage adapter."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageSessionResult,
)
from application.triage.verdict import (
    Verdict,
    VerdictParseError,
    parse_verdict,
)

_PERMISSION_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "permission": {
        "edit": "deny",
        "bash": {"*": "deny"},
        "webfetch": "deny",
        "read": {"*": "allow"},
        "write": {"*": "deny"},
    },
}


class OpenCodeTriageAgent:
    """OpenCode-backed one-shot triage adapter."""

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        with tempfile.TemporaryDirectory(prefix=".tally-oc-") as tmpdir:
            config_path = Path(tmpdir) / "opencode.json"
            config_path.write_text(json.dumps(_PERMISSION_CONFIG, indent=2))
            completed = subprocess.run(
                self._build_run_command(cwd=cwd),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(cwd),
                env={
                    **os.environ,
                    "OPENCODE_CONFIG": str(config_path),
                },
            )

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise VerdictParseError(
                f"opencode exited with code {completed.returncode}: {stderr[:200]}"
            )

        text = self._extract_text(completed.stdout)
        return parse_verdict(text, expected_finding_id=finding_id)

    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult:
        raise NotImplementedError("use run_triage")

    def _build_run_command(self, *, cwd: Path) -> list[str]:
        return [
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--dir",
            str(cwd),
            "--format",
            "json",
        ]

    def _extract_text(self, stdout: str) -> str:
        if not stdout.strip():
            raise VerdictParseError("empty stdout from opencode")
        chunks: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") != "text":
                continue
            part = obj.get("part")
            if isinstance(part, dict):
                txt = part.get("text")
                if isinstance(txt, str):
                    chunks.append(txt)
        if not chunks:
            raise VerdictParseError("no text events in opencode output")
        return "".join(chunks)

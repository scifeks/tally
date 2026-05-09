"""OpenCode-backed one-shot triage adapter."""

from __future__ import annotations

import json
import subprocess
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

_OC_CONFIG_PATH = "/etc/opencode/opencode.json"


class OpenCodeTriageAgent:
    """OpenCode-backed one-shot triage adapter."""

    def __init__(
        self,
        *,
        compose_path: Path,
        model: str = "",
        provider_name: str = "ollama",
    ) -> None:
        self._compose_path = compose_path
        self._model = model
        self._provider_name = provider_name
        self.last_raw_output: str = ""

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
        cmd = [
            "docker",
            "compose",
            "-f",
            str(self._compose_path),
            "exec",
            "-T",
            "-e",
            f"OPENCODE_CONFIG={_OC_CONFIG_PATH}",
            "triage-agent",
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--dir",
            "/workspace",
            "--format",
            "json",
        ]
        if self._model:
            cmd.extend(["--model", f"{self._provider_name}/{self._model}"])
        completed = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise VerdictParseError(
                f"opencode exited with code {completed.returncode}: {stderr[:200]}"
            )

        self.last_raw_output = completed.stdout
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

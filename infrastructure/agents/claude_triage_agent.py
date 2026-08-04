"""Claude-backed one-shot triage adapter."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageSessionResult,
)
from domain.triage.verdict import Verdict, VerdictParseError, parse_verdict


class ClaudeTriageAgent:
    def __init__(self, *, model: str, compose_path: Path) -> None:
        self._model = model
        self._compose_path = compose_path
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
        completed = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self._compose_path),
                "exec",
                "-T",
                "triage-agent",
                "claude",
                "--print",
                "--output-format",
                "text",
                "--dangerously-skip-permissions",
                "--model",
                self._model,
                "--add-dir",
                "/workspace",
                "--tools",
                "Read,Grep,Glob,Bash",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise VerdictParseError(
                f"claude exited with code {completed.returncode}: {stderr[:200]}"
            )

        self.last_raw_output = completed.stdout
        result_text = self._extract_result(completed.stdout)
        return parse_verdict(result_text, expected_finding_id=finding_id)

    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult:
        raise NotImplementedError("use run_triage")

    def _extract_result(self, stdout: str) -> str:
        if not stdout.strip():
            raise VerdictParseError("empty stdout from claude")
        return stdout.strip()

"""Claude-backed one-shot triage adapter."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageSessionResult,
)
from application.triage.verdict import Verdict, VerdictParseError, parse_verdict


class ClaudeTriageAgent:
    def __init__(self, *, model: str) -> None:
        self._model = model

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
                "claude",
                "--print",
                "--output-format",
                "json",
                "--dangerously-skip-permissions",
                "--model",
                self._model,
                "--add-dir",
                str(cwd),
                "--tools",
                "",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(cwd),
        )

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise VerdictParseError(
                f"claude exited with code {completed.returncode}: {stderr[:200]}"
            )

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

        try:
            wrapper = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise VerdictParseError(f"claude output is not valid JSON: {exc}") from exc

        if not isinstance(wrapper, dict):
            raise VerdictParseError(
                f"claude output is not an object: {type(wrapper).__name__}"
            )

        if wrapper.get("is_error"):
            raise VerdictParseError(
                f"claude reported an error: {wrapper.get('result', 'unknown')}"
            )

        result = wrapper.get("result")
        if not isinstance(result, str):
            raise VerdictParseError(
                f"claude wrapper missing 'result' string field; "
                f"keys={list(wrapper.keys())}"
            )

        return result

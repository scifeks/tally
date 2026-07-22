"""Claude-backed LLM scan adapter for security vulnerability detection."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from application.llm_scan.findings_parser import parse_llm_findings
from application.ports.llm_scan_backend import (
    LlmScanResult,
    PreparedLlmScanSession,
)


class ClaudeLlmScanAdapter:
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
        yield PreparedLlmScanSession(cwd=app_root)

    def run_scan(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> LlmScanResult:
        """Run Claude inside Docker container to scan codebase.

        Args:
            prompt: The security scan prompt to send to Claude.
            timeout_seconds: Maximum time to wait for completion.
            cwd: Working directory for the scan.

        Returns:
            LlmScanResult with success flag, parsed findings, and output.
        """
        try:
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
                    "json",
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
        except subprocess.TimeoutExpired:
            return LlmScanResult(
                success=False,
                findings=[],
                raw_output="",
                error="timeout",
            )

        self.last_raw_output = completed.stdout

        if completed.returncode != 0:
            return LlmScanResult(
                success=False,
                findings=[],
                raw_output=completed.stdout,
                error=completed.stderr.strip() if completed.stderr else "",
            )

        try:
            result_text = self._extract_result(completed.stdout)
        except ValueError as exc:
            return LlmScanResult(
                success=False,
                findings=[],
                raw_output=completed.stdout,
                error=str(exc),
            )

        findings, parse_errors = parse_llm_findings(result_text)

        return LlmScanResult(
            success=True,
            findings=findings,
            raw_output=completed.stdout,
            error="; ".join(parse_errors) if parse_errors else None,
        )

    def _extract_result(self, stdout: str) -> str:
        """Extract the result string from Claude's JSON wrapper output.

        Args:
            stdout: The raw stdout from Claude.

        Returns:
            The extracted result string.

        Raises:
            ValueError: If output cannot be parsed or is malformed.
        """
        if not stdout.strip():
            raise ValueError("empty stdout from claude")

        try:
            wrapper = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"claude output is not valid JSON: {exc}") from exc

        if not isinstance(wrapper, dict):
            raise ValueError(
                f"claude output is not an object: {type(wrapper).__name__}"
            )

        if wrapper.get("is_error"):
            raise ValueError(
                f"claude reported an error: {wrapper.get('result', 'unknown')}"
            )

        result = wrapper.get("result")
        if not isinstance(result, str):
            raise ValueError(
                f"claude wrapper missing 'result' string field; "
                f"keys={list(wrapper.keys())}"
            )

        return result

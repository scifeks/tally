"""Claude-backed one-shot triage adapter."""

from __future__ import annotations

import base64
import json
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageSessionResult,
)
from domain.triage.verdict import (
    Verdict,
    VerdictParseError,
    parse_verdict,
)

_TIMEOUT_EXIT_CODE = 124


class ClaudeTriageAgent:
    """Claude-backed triage adapter with persistent relay."""

    def __init__(self, *, model: str, compose_path: Path) -> None:
        self._model = model
        self._compose_path = compose_path
        self.last_raw_output: str = ""
        self._relay_proc: subprocess.Popen[str] | None = None

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        self._relay_proc = subprocess.Popen(
            [
                "docker",
                "compose",
                "-f",
                str(self._compose_path),
                "exec",
                "-T",
                "triage-agent",
                "triage-relay",
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
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            yield PreparedTriageSession(cwd=app_root)
        finally:
            self._stop_relay()

    def _stop_relay(self) -> None:
        proc = self._relay_proc
        self._relay_proc = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        if self._relay_proc is None:
            raise RuntimeError("No relay process")
        if self._relay_proc.poll() is not None:
            raise RuntimeError("Relay process exited")

        b64_prompt = base64.b64encode(prompt.encode()).decode()
        try:
            assert self._relay_proc.stdin is not None
            self._relay_proc.stdin.write(f"{timeout_seconds}\n{b64_prompt}\n")
            self._relay_proc.stdin.flush()
        except BrokenPipeError:
            raise RuntimeError("Relay process died") from None

        line = self._read_response(timeout_seconds)

        result = json.loads(line)
        rc = result["rc"]
        stdout = base64.b64decode(result["out"]).decode()
        stderr = base64.b64decode(result["err"]).decode()

        if rc == _TIMEOUT_EXIT_CODE:
            raise subprocess.TimeoutExpired(cmd=["claude"], timeout=timeout_seconds)

        if rc != 0:
            raise VerdictParseError(f"claude exited with code {rc}: {stderr[:200]}")

        self.last_raw_output = stdout
        result_text = self._extract_result(stdout)
        return parse_verdict(result_text, expected_finding_id=finding_id)

    def _read_response(self, timeout_seconds: int) -> str:
        proc = self._relay_proc
        assert proc is not None
        deadline = timeout_seconds + 30
        timed_out = threading.Event()

        def _kill_on_timeout() -> None:
            timed_out.set()
            if proc.poll() is None:
                proc.kill()

        timer = threading.Timer(deadline, _kill_on_timeout)
        timer.start()
        try:
            assert proc.stdout is not None
            line = proc.stdout.readline()
        finally:
            timer.cancel()

        if timed_out.is_set() or not line:
            raise subprocess.TimeoutExpired(
                cmd=["triage-relay"],
                timeout=timeout_seconds,
            )
        return line

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

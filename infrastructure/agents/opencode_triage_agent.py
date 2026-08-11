"""OpenCode-backed one-shot triage adapter."""

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

_OC_CONFIG_PATH = "/etc/opencode/opencode.json"
_TIMEOUT_EXIT_CODE = 124


class OpenCodeTriageAgent:
    """OpenCode-backed triage adapter with persistent relay."""

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
        self._relay_proc: subprocess.Popen[str] | None = None

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
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
            "triage-relay",
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--dir",
            "/workspace",
            "--format",
            "json",
        ]
        if self._model:
            cmd.extend(
                [
                    "--model",
                    f"{self._provider_name}/{self._model}",
                ]
            )
        self._relay_proc = subprocess.Popen(
            cmd,
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

        assert self._relay_proc.stdin is not None
        b64_prompt = base64.b64encode(prompt.encode()).decode()
        try:
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
            raise subprocess.TimeoutExpired(cmd=["opencode"], timeout=timeout_seconds)

        if rc != 0:
            raise VerdictParseError(f"opencode exited with code {rc}: {stderr[:200]}")

        self.last_raw_output = stdout
        text = self._extract_text(stdout)
        return parse_verdict(text, expected_finding_id=finding_id)

    def _read_response(self, timeout_seconds: int) -> str:
        proc = self._relay_proc
        assert proc is not None
        assert proc.stdout is not None
        deadline = timeout_seconds + 30
        timed_out = threading.Event()

        def _kill_on_timeout() -> None:
            timed_out.set()
            if proc.poll() is None:
                proc.kill()

        timer = threading.Timer(deadline, _kill_on_timeout)
        timer.start()
        try:
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

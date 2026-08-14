"""OpenCode-backed one-shot triage adapter."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageBackendUnavailable,
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
        verdict_out_path: Path,
        model: str = "",
        provider_name: str = "ollama",
    ) -> None:
        self._compose_path = compose_path
        self._verdict_out_path = verdict_out_path
        self._model = model
        self._provider_name = provider_name
        self.last_raw_output: str = ""
        self.last_relay_stderr: str = ""
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
        self.last_relay_stderr = ""
        self._set_stderr_nonblocking(self._relay_proc)
        try:
            yield PreparedTriageSession(cwd=app_root)
        finally:
            self._stop_relay()

    @staticmethod
    def _set_stderr_nonblocking(proc: subprocess.Popen[str]) -> None:
        """Best-effort switch to non-blocking stderr reads.

        The drain helpers depend on reads returning fast when no data is
        present; without this they could block the runner thread. Wrapped
        so unit tests using MagicMock processes (no real fd) still work.
        """
        stderr = proc.stderr
        if stderr is None:
            return
        try:
            fd = stderr.fileno()
        except (OSError, AttributeError, ValueError):
            return
        if not isinstance(fd, int):
            return
        try:
            os.set_blocking(fd, False)
        except (OSError, ValueError):
            return

    def _drain_relay_stderr(self) -> None:
        """Append any available stderr bytes to ``last_relay_stderr``.

        The stderr pipe is non-blocking (see ``prepare_session``), so a read
        that finds no bytes returns None or raises BlockingIOError; neither
        is fatal here.
        """
        proc = self._relay_proc
        if proc is None or proc.stderr is None:
            return
        try:
            chunk = proc.stderr.read()
        except (BlockingIOError, ValueError, OSError):
            return
        if isinstance(chunk, str) and chunk:
            self.last_relay_stderr += chunk

    def _stop_relay(self) -> None:
        proc = self._relay_proc
        self._relay_proc = None
        if proc is None:
            return
        if proc.poll() is not None:
            self._drain_dead_proc_stderr(proc)
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        self._drain_dead_proc_stderr(proc)

    def _drain_dead_proc_stderr(self, proc: subprocess.Popen[str]) -> None:
        """Read everything left in a dead relay's stderr into the buffer."""
        if proc.stderr is None:
            return
        try:
            leftover = proc.stderr.read()
        except (BlockingIOError, ValueError, OSError):
            return
        if isinstance(leftover, str) and leftover:
            self.last_relay_stderr += leftover

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        self._clear_verdict_file()
        self._dispatch_prompt(
            prompt, finding_id=finding_id, timeout_seconds=timeout_seconds
        )
        try:
            return self._load_verdict(finding_id)
        except VerdictParseError as first_err:
            retry_prompt = (
                f"{prompt}\n\nPrevious attempt failed: {first_err}. "
                f"Write the corrected JSON to /workspace/out/verdict.json."
            )
            self._clear_verdict_file()
            self._dispatch_prompt(
                retry_prompt,
                finding_id=finding_id,
                timeout_seconds=timeout_seconds,
            )
            return self._load_verdict(finding_id)

    def _dispatch_prompt(
        self, prompt: str, *, finding_id: int, timeout_seconds: int
    ) -> None:
        """Send a prompt to opencode via the relay and wait for it to exit."""
        if self._relay_proc is None:
            raise TriageBackendUnavailable("No relay process")
        exit_code = self._relay_proc.poll()
        if exit_code is not None:
            self._drain_dead_proc_stderr(self._relay_proc)
            raise TriageBackendUnavailable(
                f"Relay process already exited (rc={exit_code}) before finding "
                f"{finding_id}; stderr tail={self.last_relay_stderr[-800:]!r}"
            )
        self._drain_relay_stderr()

        assert self._relay_proc.stdin is not None
        b64_prompt = base64.b64encode(prompt.encode()).decode()
        try:
            self._relay_proc.stdin.write(f"{timeout_seconds}\n{b64_prompt}\n")
            self._relay_proc.stdin.flush()
        except BrokenPipeError:
            self._drain_dead_proc_stderr(self._relay_proc)
            raise TriageBackendUnavailable(
                f"Relay stdin closed before finding {finding_id} could be "
                f"submitted; stderr tail={self.last_relay_stderr[-800:]!r}"
            ) from None

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

    def _clear_verdict_file(self) -> None:
        try:
            self._verdict_out_path.unlink()
        except FileNotFoundError:
            pass

    def _load_verdict(self, finding_id: int) -> Verdict:
        try:
            text = self._verdict_out_path.read_text()
        except FileNotFoundError:
            raise VerdictParseError(
                f"verdict file not found at {self._verdict_out_path}"
            ) from None
        return parse_verdict(text, expected_finding_id=finding_id)

    def _read_response(self, timeout_seconds: int) -> str:
        proc = self._relay_proc
        assert proc is not None
        assert proc.stdout is not None
        deadline = timeout_seconds + 30
        client_timer_fired = threading.Event()

        def _kill_on_timeout() -> None:
            client_timer_fired.set()
            if proc.poll() is None:
                proc.kill()

        timer = threading.Timer(deadline, _kill_on_timeout)
        timer.start()
        try:
            line = proc.stdout.readline()
        finally:
            timer.cancel()

        if not line:
            self._drain_dead_proc_stderr(proc)
            stderr_tail = self.last_relay_stderr[-800:]
            if client_timer_fired.is_set():
                raise subprocess.TimeoutExpired(
                    cmd=["triage-relay:client-killed"],
                    timeout=timeout_seconds,
                    output=(
                        f"client-side deadline ({deadline}s) elapsed before "
                        f"relay produced a response; SIGKILL'd relay; "
                        f"stderr tail={stderr_tail!r}"
                    ).encode(),
                )
            rc = proc.poll()
            raise TriageBackendUnavailable(
                f"relay closed stdout with no response (rc={rc}); "
                f"stderr tail={stderr_tail!r}"
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

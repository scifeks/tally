"""Host-side relay client wrapping a long-lived docker compose exec."""

from __future__ import annotations

import logging
import selectors
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NoReturn

from infrastructure.anthropic.sdk_relay.events import (
    EndEvent,
    Event,
    EventParseError,
    parse_event,
)
from infrastructure.anthropic.sdk_relay.job_spec import (
    JobSpec,
    ScanJobSpec,
    TriageJobSpec,
    serialize_spec,
)

_log = logging.getLogger(__name__)

_TIMEOUT_GRACE_SECONDS = 30


class SDKRelayUnavailable(RuntimeError):
    """Raised when the relay process is dead or unreachable."""


class SDKRelayClient:
    """Owns a long-lived `docker compose exec -T` process."""

    def __init__(
        self,
        *,
        compose_path: Path | None,
        service_name: str = "sdk-sidecar",
        process_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._compose_path = compose_path
        self._service_name = service_name
        self._process_factory = process_factory
        self._proc: Any | None = None
        self._stderr_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._proc is not None:
                return
            self._proc = (
                self._process_factory() if self._process_factory else self._spawn_exec()
            )
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, args=(self._proc,), daemon=True
            )
            self._stderr_thread.start()

    @staticmethod
    def _drain_stderr(proc: Any) -> None:
        # An unread pipe fills at 64 KB and blocks the child's stderr writes.
        stream = getattr(proc, "stderr", None)
        if stream is None:
            return
        try:
            for line in stream:
                _log.warning("sdk-relay stderr: %s", line.rstrip("\n"))
        except (OSError, ValueError):
            return

    def _spawn_exec(self) -> subprocess.Popen[str]:
        if self._compose_path is None:
            raise SDKRelayUnavailable("compose_path required to spawn relay")
        return subprocess.Popen(
            [
                "docker",
                "compose",
                "-f",
                str(self._compose_path),
                "exec",
                "-T",
                self._service_name,
                "sdk-runner",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def submit(self, spec: JobSpec) -> Iterator[Event]:
        with self._lock:
            proc = self._proc
        if proc is None:
            raise SDKRelayUnavailable("relay not started")
        returncode = proc.poll()
        if returncode is not None:
            raise SDKRelayUnavailable(f"relay exited (rc={returncode})")
        payload = serialize_spec(spec) + "\n"
        try:
            proc.stdin.write(payload)
            proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise SDKRelayUnavailable("relay stdin closed") from exc

        return self._iter_until_end(proc, spec.timeout_seconds)

    def _iter_until_end(self, proc: Any, timeout_seconds: int) -> Iterator[Event]:
        # Absolute budget so a runner trickling events cannot extend the wait forever.
        deadline = time.monotonic() + timeout_seconds + _TIMEOUT_GRACE_SECONDS
        selector: selectors.BaseSelector | None = selectors.DefaultSelector()
        try:
            selector.register(proc.stdout, selectors.EVENT_READ)
        except (ValueError, AttributeError):
            # In-memory streams have no fileno; fall back to blocking reads.
            selector.close()
            selector = None

        try:
            while True:
                line = self._readline_with_timeout(proc, deadline, selector)
                if not line:
                    self._fail_stalled(proc, timeout_seconds)
                try:
                    event = parse_event(line.strip())
                except EventParseError:
                    _log.warning("sdk-relay: dropping unparseable line: %r", line)
                    continue
                yield event
                if isinstance(event, EndEvent):
                    return
        finally:
            if selector is not None:
                selector.close()

    def _fail_stalled(self, proc: Any, timeout_seconds: int) -> NoReturn:
        """Classify a stall, then discard the process so stale events cannot leak."""
        returncode = proc.poll()
        if returncode is not None:
            self._discard(proc)
            raise SDKRelayUnavailable(f"relay exited mid-job (rc={returncode})")
        # Leftover events from this job would be read as the next job's output.
        proc.kill()
        self._discard(proc)
        raise subprocess.TimeoutExpired(cmd=["sdk-relay"], timeout=timeout_seconds)

    def _discard(self, proc: Any) -> None:
        with self._lock:
            if self._proc is proc:
                self._proc = None

    def _readline_with_timeout(
        self, proc: Any, deadline: float, selector: selectors.BaseSelector | None
    ) -> str:
        if selector is not None:
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(timeout=remaining):
                return ""
        elif time.monotonic() >= deadline:
            return ""
        return proc.stdout.readline()

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            stderr_thread = self._stderr_thread
            self._stderr_thread = None
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except OSError:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if stderr_thread is not None:
            stderr_thread.join(timeout=5)

    def __enter__(self) -> SDKRelayClient:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()


__all__ = [
    "SDKRelayClient",
    "SDKRelayUnavailable",
    "TriageJobSpec",
    "ScanJobSpec",
]

"""Protocol-level tests for SDKRelayClient."""

from __future__ import annotations

import io
import json
import subprocess
import time

import pytest

from infrastructure.anthropic.sdk_relay import client as client_module
from infrastructure.anthropic.sdk_relay.client import (
    SDKRelayClient,
    SDKRelayUnavailable,
    TriageJobSpec,
)
from infrastructure.anthropic.sdk_relay.events import (
    AssistantTextEvent,
    EndEvent,
    ErrorEvent,
    ResultEvent,
)


class _FakeProc:
    """In-memory stand-in for subprocess.Popen used by the client."""

    def __init__(self, event_lines: list[str], stderr_text: str = "") -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("\n".join(event_lines) + "\n")
        self.stderr = io.StringIO(stderr_text)
        self._alive = True
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return None if self._alive else 0

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False

    def kill(self) -> None:
        self.killed = True
        self._alive = False

    def wait(self, timeout: float | None = None) -> int:
        self._alive = False
        return 0


def _spec() -> TriageJobSpec:
    return TriageJobSpec(
        model="opus",
        system_prompt="sys",
        user_prompt="user",
        allowed_tools=["Read"],
        cwd="/workspace/repos/x",
        timeout_seconds=60,
    )


def test_happy_path_yields_events_in_order() -> None:
    proc = _FakeProc(
        [
            json.dumps({"type": "assistant_text", "text": "thinking"}),
            json.dumps({"type": "result", "text": "{}", "is_error": False}),
            json.dumps({"type": "end"}),
        ]
    )
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    events = list(client.submit(_spec()))
    assert events == [
        AssistantTextEvent(text="thinking"),
        ResultEvent(text="{}", is_error=False),
        EndEvent(),
    ]


def test_two_jobs_isolate_errors() -> None:
    """A 429 on job 1 does not poison job 2.

    This test nails the design's isolation guarantee: one job's error
    event is scoped to that submit() iterator; the next submit() reads
    its own event stream.
    """
    proc = _FakeProc(
        [
            # job 1
            json.dumps(
                {
                    "type": "error",
                    "status_code": 429,
                    "subtype": "rate_limit",
                    "message": "slow",
                }
            ),
            json.dumps({"type": "end"}),
            # job 2
            json.dumps({"type": "result", "text": '{"ok":1}', "is_error": False}),
            json.dumps({"type": "end"}),
        ]
    )
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    job1 = list(client.submit(_spec()))
    assert any(isinstance(e, ErrorEvent) for e in job1)
    job2 = list(client.submit(_spec()))
    assert any(isinstance(e, ResultEvent) and not e.is_error for e in job2)


def test_dead_process_raises_relay_unavailable() -> None:
    proc = _FakeProc([])
    proc._alive = False  # simulate crash before any event
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    with pytest.raises(SDKRelayUnavailable):
        list(client.submit(_spec()))


def test_host_side_timeout_raises_timeout_expired() -> None:
    class _StallProc(_FakeProc):
        def __init__(self) -> None:
            super().__init__([])

    proc = _StallProc()
    client = SDKRelayClient(
        compose_path=None,
        service_name="sdk",
        process_factory=lambda: proc,
    )
    client.start()
    spec = TriageJobSpec(
        model="opus",
        system_prompt="",
        user_prompt="",
        allowed_tools=[],
        cwd="/x",
        timeout_seconds=1,
    )
    with pytest.raises(subprocess.TimeoutExpired):
        list(client.submit(spec))


def test_stop_closes_stdin_and_waits() -> None:
    proc = _FakeProc([])
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    client.stop()
    assert proc.stdin.closed
    assert proc.terminated


def _stall_spec() -> TriageJobSpec:
    return TriageJobSpec(
        model="opus",
        system_prompt="",
        user_prompt="",
        allowed_tools=[],
        cwd="/x",
        timeout_seconds=1,
    )


def test_timeout_kills_process_and_poisons_client() -> None:
    proc = _FakeProc([])
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    with pytest.raises(subprocess.TimeoutExpired):
        list(client.submit(_stall_spec()))
    assert proc.killed
    assert client._proc is None
    with pytest.raises(SDKRelayUnavailable):
        client.submit(_spec())


def test_timeout_classifies_dead_process_as_unavailable() -> None:
    class _DiesDuringJob(_FakeProc):
        def __init__(self) -> None:
            super().__init__([])
            self.polls = 0

        def poll(self) -> int | None:
            # Alive for the pre-submit check, dead once the stall is classified.
            self.polls += 1
            return None if self.polls == 1 else 1

    proc = _DiesDuringJob()
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    with pytest.raises(SDKRelayUnavailable):
        list(client.submit(_stall_spec()))
    assert client._proc is None


def test_total_deadline_bounds_trickling_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TricklingProc(_FakeProc):
        def __init__(self) -> None:
            super().__init__([])
            self.stdout = io.StringIO(
                json.dumps({"type": "assistant_text", "text": "x"}) + "\n"
            )

    clock = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(clock))
    proc = _TricklingProc()
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    iterator = client.submit(_stall_spec())
    assert isinstance(next(iterator), AssistantTextEvent)
    with pytest.raises(subprocess.TimeoutExpired):
        next(iterator)
    assert proc.killed


def test_stderr_drained_in_background(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[str] = []
    monkeypatch.setattr(
        client_module._log,
        "warning",
        lambda msg, *args: logged.append(msg % args if args else msg),
    )
    proc = _FakeProc([], stderr_text="boom one\nboom two\n")
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    deadline = time.monotonic() + 5
    while len(logged) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    client.stop()
    assert "sdk-relay stderr: boom one" in logged
    assert "sdk-relay stderr: boom two" in logged


def test_submit_after_stop_raises_unavailable() -> None:
    proc = _FakeProc([])
    client = SDKRelayClient(
        compose_path=None, service_name="sdk", process_factory=lambda: proc
    )
    client.start()
    client.stop()
    with pytest.raises(SDKRelayUnavailable):
        client.submit(_spec())

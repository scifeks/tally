import atexit
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from application.ports.triage_agent import TriageBackendUnavailable
from application.triage.prompts.output_instructions import STDOUT_OUTPUT_INSTRUCTION
from application.triage.prompts.triage_prompt import TriagePrompt
from domain.triage.verdict import Verdict
from infrastructure.anthropic import claude_sdk_triage_agent
from infrastructure.anthropic.claude_sdk_triage_agent import AgentSDKTriageAgent
from infrastructure.anthropic.error_classifier import ErrorClass
from infrastructure.anthropic.sdk_relay.client import (
    SDKRelayClient,
    SDKRelayUnavailable,
)
from infrastructure.anthropic.sdk_relay.events import (
    AssistantTextEvent,
    EndEvent,
    ErrorEvent,
    Event,
    ResultEvent,
)
from infrastructure.anthropic.sdk_relay.job_spec import JobSpec, TriageJobSpec


def _fake_prompt(label: str = "p") -> TriagePrompt:
    return TriagePrompt(
        preamble=f"preamble for {label}",
        finding_data=f"finding data for {label}",
        guidance=f"guidance for {label}",
    )


def _make_valid_verdict_json(finding_id: int = 1) -> str:
    return (
        '{"finding_id": ' + str(finding_id) + ","
        '"confidence": "confirmed",'
        '"finding_type": "vulnerability",'
        '"severity": "high",'
        '"access_required": "none",'
        '"exploitation_complexity": "low",'
        '"user_interaction": "none",'
        '"reasoning": "Observed concatenation.",'
        '"remediation": "Use parameterized queries.",'
        '"attack_vector": "network",'
        '"call_stack": []}'
    )


def _install_relay(
    monkeypatch: pytest.MonkeyPatch,
    submit: Callable[[SDKRelayClient, JobSpec], Iterator[Event]],
) -> None:
    monkeypatch.setattr(SDKRelayClient, "submit", submit)
    monkeypatch.setattr(SDKRelayClient, "start", lambda self: None)
    monkeypatch.setattr(SDKRelayClient, "stop", lambda self: None)


def _agent(tmp_path: Path) -> AgentSDKTriageAgent:
    return AgentSDKTriageAgent(
        billing_method="plan",
        api_key_source=None,
        model="x",
        compose_path=tmp_path / "docker-compose.yaml",
    )


def _run(agent: AgentSDKTriageAgent, tmp_path: Path, timeout: int = 60) -> Verdict:
    with agent.prepare_session(project="demo", run_id=1, app_root=tmp_path):
        return agent.run_triage(
            _fake_prompt(),
            finding_id=1,
            timeout_seconds=timeout,
            cwd=tmp_path,
        )


def test_run_triage_consumes_relay_result_and_builds_spec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[JobSpec] = []

    def fake_submit(self: SDKRelayClient, spec: JobSpec) -> Iterator[Event]:
        captured.append(spec)
        return iter(
            [
                AssistantTextEvent(text="working"),
                ResultEvent(text=_make_valid_verdict_json(1), is_error=False),
                EndEvent(),
            ]
        )

    _install_relay(monkeypatch, fake_submit)
    verdict = _run(_agent(tmp_path), tmp_path)

    assert verdict.finding_id == 1
    spec = captured[0]
    assert isinstance(spec, TriageJobSpec)
    assert spec.user_prompt == "finding data for p"
    assert spec.system_prompt == _fake_prompt().instructions
    assert spec.timeout_seconds == 60
    assert spec.cwd == str(tmp_path)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        pytest.param(
            ErrorEvent(status_code=429, subtype="api_error", message="overloaded"),
            ErrorClass.RATE_LIMIT_PLAN,
            id="rate_limit",
        ),
        pytest.param(
            ErrorEvent(status_code=401, subtype="api_error", message="bad key"),
            ErrorClass.AUTH_FAILURE,
            id="auth",
        ),
        pytest.param(
            ErrorEvent(status_code=None, subtype="timeout", message="timed out"),
            ErrorClass.UNKNOWN,
            id="timeout_event_without_status",
        ),
    ],
)
def test_error_event_is_classified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event: ErrorEvent,
    expected: ErrorClass,
) -> None:
    _install_relay(monkeypatch, lambda self, spec: iter([event, EndEvent()]))

    with pytest.raises(TriageBackendUnavailable) as info:
        _run(_agent(tmp_path), tmp_path)
    assert info.value.error_class is expected


def test_error_result_is_classified_not_parsed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_relay(
        monkeypatch,
        lambda self, spec: iter([ResultEvent(text="boom", is_error=True), EndEvent()]),
    )

    with pytest.raises(TriageBackendUnavailable) as info:
        _run(_agent(tmp_path), tmp_path)
    assert info.value.error_class is ErrorClass.UNKNOWN


def test_dead_relay_maps_to_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def dead_submit(self: SDKRelayClient, spec: JobSpec) -> Iterator[Event]:
        raise SDKRelayUnavailable("relay exited")

    _install_relay(monkeypatch, dead_submit)

    with pytest.raises(TriageBackendUnavailable) as info:
        _run(_agent(tmp_path), tmp_path)
    assert info.value.error_class is ErrorClass.UNKNOWN


def test_timeout_expired_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def slow_submit(self: SDKRelayClient, spec: JobSpec) -> Iterator[Event]:
        raise subprocess.TimeoutExpired(cmd="sdk-runner", timeout=spec.timeout_seconds)

    _install_relay(monkeypatch, slow_submit)

    with pytest.raises(subprocess.TimeoutExpired) as info:
        _run(_agent(tmp_path), tmp_path, timeout=120)
    assert info.value.timeout == 120


def test_run_triage_without_prepare_session_starts_relay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: list[bool] = []
    _install_relay(
        monkeypatch,
        lambda self, spec: iter(
            [ResultEvent(text=_make_valid_verdict_json(1), is_error=False), EndEvent()]
        ),
    )
    monkeypatch.setattr(SDKRelayClient, "start", lambda self: started.append(True))

    verdict = _agent(tmp_path).run_triage(
        _fake_prompt(), finding_id=1, timeout_seconds=1, cwd=tmp_path
    )
    assert verdict.finding_id == 1
    assert started == [True]


def _raise_unavailable(self: SDKRelayClient) -> None:
    raise SDKRelayUnavailable("docker missing")


def test_prepare_session_start_failure_translates_to_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SDKRelayClient, "start", _raise_unavailable)

    with pytest.raises(TriageBackendUnavailable) as info:
        with _agent(tmp_path).prepare_session(
            project="demo", run_id=1, app_root=tmp_path
        ):
            pass
    assert info.value.error_class is ErrorClass.UNKNOWN


def test_lazy_start_failure_translates_to_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SDKRelayClient, "start", _raise_unavailable)

    with pytest.raises(TriageBackendUnavailable) as info:
        _agent(tmp_path).run_triage(
            _fake_prompt(), finding_id=1, timeout_seconds=1, cwd=tmp_path
        )
    assert info.value.error_class is ErrorClass.UNKNOWN


def test_lazy_start_registers_atexit_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_relay(
        monkeypatch,
        lambda self, spec: iter(
            [ResultEvent(text=_make_valid_verdict_json(1), is_error=False), EndEvent()]
        ),
    )
    registered: list[object] = []
    monkeypatch.setattr(atexit, "register", registered.append)
    agent = _agent(tmp_path)

    agent.run_triage(_fake_prompt(), finding_id=1, timeout_seconds=1, cwd=tmp_path)

    client = agent._client
    assert client is not None
    assert registered == [client.stop]


def test_api_mode_requires_api_key_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        AgentSDKTriageAgent(
            billing_method="api",
            api_key_source=None,
            model="x",
            compose_path=tmp_path / "docker-compose.yaml",
        )


def test_class_exposes_stdout_output_instruction() -> None:
    assert (
        claude_sdk_triage_agent.AgentSDKTriageAgent.OUTPUT_INSTRUCTION
        == STDOUT_OUTPUT_INSTRUCTION
    )

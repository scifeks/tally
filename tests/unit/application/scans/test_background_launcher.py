"""Tests for ScanBackgroundLauncher orchestration and _run_scan_via_relay wiring."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from application.anthropic.mode_availability import BackgroundModeAvailability
from application.scans.background_launcher import (
    ScanBackgroundLauncher,
    ScanConfigurationError,
    _build_prompt,
    _run_scan_via_relay,
    _SDKRuntimeError,
)
from application.triage.compose import COMPOSE_RELATIVE_PATH
from infrastructure.anthropic.error_classifier import ErrorClass, classify
from infrastructure.anthropic.sdk_relay.events import (
    EndEvent,
    ErrorEvent,
    Event,
    ResultEvent,
)
from infrastructure.anthropic.sdk_relay.job_spec import ScanJobSpec


def _mk_availability(*, oauth_available: bool, api_key_available: bool) -> MagicMock:
    svc = MagicMock()
    svc.evaluate.return_value = BackgroundModeAvailability(
        oauth_available=oauth_available,
        api_key_available=api_key_available,
        interactive_available=True,
        oauth_reason=None if oauth_available else "no session",
        api_key_reason=None if api_key_available else "no key",
    )
    return svc


def _mk_config(
    default_billing: str | None,
    *,
    mcp_host: str = "127.0.0.1",
    mcp_port: int = 8765,
) -> MagicMock:
    cfg = MagicMock()
    cfg.claude.default_billing_method = default_billing
    cfg.claude.api_key = ""
    cfg.claude.model = "claude-opus-4-6[1m]"
    cfg.mcp.host = mcp_host
    cfg.mcp.port = mcp_port
    return cfg


def _mk_mcp_service(
    completed_phases: list[str] | None = None,
    latest_execution_per_phase: dict[str, dict[str, object]] | None = None,
) -> MagicMock:
    svc = MagicMock()
    svc.get_scan_phase_status.return_value = {
        "completed_phases": completed_phases or [],
        "latest_execution_per_phase": latest_execution_per_phase or {},
    }
    return svc


def _mk_repo(name: str = "my-app", path: str = "/repos/my-app") -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.path = path
    return repo


def _default_launch_kwargs(
    **overrides: object,
) -> dict:
    defaults: dict = {
        "run_id": 1,
        "project_name": "p",
        "base_path": "/data/tally",
        "interaction_mode": "background",
        "billing_method": "plan",
        "only": ["scan-xss-stored"],
        "exclude": None,
        "adversarial": False,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Launch orchestration tests
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_launch_writes_scan_config_and_runs_skill(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    mcp_service = _mk_mcp_service()
    launcher = ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    mcp_service.set_scan_config.assert_called_once()
    args = mcp_service.set_scan_config.call_args.kwargs
    assert args["only"] == ["scan-xss-stored"]
    assert args["adversarial_verification"] is False


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_launch_cwd_equals_primary_repo_path(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo(path="/repos/target")]
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    assert mock_run.call_args.args[0].cwd == "/repos/target"


def test_launch_rejects_api_without_key() -> None:
    launcher = ScanBackgroundLauncher(
        mcp_service=MagicMock(),
        availability=_mk_availability(oauth_available=True, api_key_available=False),
        config=_mk_config(default_billing=None),
    )
    with pytest.raises(ValueError, match="api billing unavailable"):
        launcher.launch(**_default_launch_kwargs(billing_method="api"))


def test_launch_rejects_non_background_mode() -> None:
    launcher = ScanBackgroundLauncher(
        mcp_service=MagicMock(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    with pytest.raises(ValueError, match="only handles background mode"):
        launcher.launch(**_default_launch_kwargs(interaction_mode="interactive"))


@patch("application.scans.background_launcher.load_active_repos")
def test_launch_raises_when_no_active_repos(mock_repos: MagicMock) -> None:
    mock_repos.return_value = []
    launcher = ScanBackgroundLauncher(
        mcp_service=MagicMock(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    with pytest.raises(ScanConfigurationError, match="has no active repos"):
        launcher.launch(**_default_launch_kwargs())


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_launch_cleans_up_in_progress_phases_on_crash(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    err = RuntimeError("rate limit exceeded")
    err.status_code = 429  # type: ignore[attr-defined]
    mock_run.side_effect = err
    mock_repos.return_value = [_mk_repo()]
    scan_phase_repo = MagicMock()
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
        scan_phase_repo=scan_phase_repo,
    )
    handle = launcher.launch(**_default_launch_kwargs())
    result = handle.result.result(timeout=5)
    assert result == "terminated"

    scan_phase_repo.mark_in_progress_failed.assert_called_once_with(
        run_id=1, error_class="RATE_LIMIT_PLAN"
    )


def test_launch_defaults_to_plan_billing() -> None:
    launcher = ScanBackgroundLauncher(
        mcp_service=MagicMock(),
        availability=_mk_availability(oauth_available=False, api_key_available=True),
        config=_mk_config(default_billing=None),
    )
    with pytest.raises(ValueError, match="plan billing unavailable"):
        launcher.launch(**_default_launch_kwargs(billing_method=None))


# ---------------------------------------------------------------------------
# Resume preamble tests
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_resume_preamble_included_when_phases_in_progress(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    mcp_service = _mk_mcp_service(
        completed_phases=["discovery"],
        latest_execution_per_phase={
            "discovery": {"status": "completed"},
            "xss": {"status": "in_progress"},
        },
    )
    launcher = ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    prompt = mock_run.call_args.args[0].user_prompt
    assert "Resume:" in prompt
    assert "discovery" in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_resume_preamble_included_when_phases_rate_limited(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    mcp_service = _mk_mcp_service(
        completed_phases=["discovery"],
        latest_execution_per_phase={
            "discovery": {"status": "completed"},
            "injection": {"status": "rate_limited"},
        },
    )
    launcher = ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    prompt = mock_run.call_args.args[0].user_prompt
    assert "Resume:" in prompt
    assert "discovery" in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_resume_preamble_omitted_when_only_completed(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    mcp_service = _mk_mcp_service(
        completed_phases=["discovery", "xss"],
        latest_execution_per_phase={
            "discovery": {"status": "completed"},
            "xss": {"status": "completed"},
        },
    )
    launcher = ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    prompt = mock_run.call_args.args[0].user_prompt
    assert "Resume:" not in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_resume_preamble_omitted_when_no_prior_phases(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    mcp_service = _mk_mcp_service(
        completed_phases=[],
        latest_execution_per_phase={},
    )
    launcher = ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    prompt = mock_run.call_args.args[0].user_prompt
    assert "Resume:" not in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_launch_calls_set_scan_config_before_sdk_session(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    """set_scan_config must be called before the SDK session starts."""
    mock_repos.return_value = [_mk_repo()]
    call_order: list[str] = []
    mcp_service = _mk_mcp_service()
    mcp_service.set_scan_config.side_effect = lambda **kw: call_order.append(
        "set_config"
    )
    mock_run.side_effect = lambda *a, **kw: call_order.append("sdk_run")

    launcher = ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    assert call_order == ["set_config", "sdk_run"]


# ---------------------------------------------------------------------------
# _build_prompt unit tests
# ---------------------------------------------------------------------------


def test_build_prompt_fresh_run() -> None:
    prompt = _build_prompt(
        "/tally-scan-external",
        run_id=42,
        project_name="acme",
        only=["xss-stored"],
        exclude=None,
        adversarial=True,
        completed_phases=[],
    )
    assert "Resume:" not in prompt
    assert "only=xss-stored" in prompt
    assert "adversarial=true" in prompt
    assert "Project: acme" in prompt
    assert "Run id: 42" in prompt


def test_build_prompt_resume_run() -> None:
    prompt = _build_prompt(
        "/tally-scan-external",
        run_id=7,
        project_name="acme",
        only=None,
        exclude=["csrf"],
        adversarial=False,
        completed_phases=["discovery", "xss"],
    )
    assert "Resume:" in prompt
    assert "discovery, xss" in prompt
    assert "exclude=csrf" in prompt
    assert "adversarial=false" in prompt


# ---------------------------------------------------------------------------
# _run_scan_via_relay
# ---------------------------------------------------------------------------


class _FakeRelayClient:
    """Stands in for SDKRelayClient; events are set per test."""

    events: ClassVar[list[Event]] = []
    instances: ClassVar[list[_FakeRelayClient]] = []

    def __init__(self, *, compose_path: Path) -> None:
        self.compose_path = compose_path
        self.started = False
        self.stopped = False
        self.specs: list[ScanJobSpec] = []
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True

    def submit(self, spec: ScanJobSpec) -> Iterator[Event]:
        self.specs.append(spec)
        return iter(type(self).events)

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def fake_relay(monkeypatch: pytest.MonkeyPatch) -> type[_FakeRelayClient]:
    _FakeRelayClient.events = []
    _FakeRelayClient.instances = []
    monkeypatch.setattr(
        "application.scans.background_launcher.SDKRelayClient", _FakeRelayClient
    )
    return _FakeRelayClient


def _mk_spec() -> ScanJobSpec:
    return ScanJobSpec(
        model="x",
        user_prompt="p",
        allowed_tools=["Read"],
        cwd="/tmp",
        timeout_seconds=60,
    )


def test_relay_happy_path_submits_spec_and_stops_client(
    fake_relay: type[_FakeRelayClient],
) -> None:
    fake_relay.events = [ResultEvent(text="ok", is_error=False), EndEvent()]
    spec = _mk_spec()

    _run_scan_via_relay(spec, compose_path=Path("/app/compose.yaml"))

    (client,) = fake_relay.instances
    assert client.specs == [spec]
    assert client.compose_path == Path("/app/compose.yaml")
    assert client.started
    assert client.stopped


def test_relay_error_event_raises_with_status_code_and_stops_client(
    fake_relay: type[_FakeRelayClient],
) -> None:
    fake_relay.events = [
        ErrorEvent(status_code=429, subtype="rate_limit", message="slow down"),
        EndEvent(),
    ]

    with pytest.raises(_SDKRuntimeError) as info:
        _run_scan_via_relay(_mk_spec(), compose_path=Path("/app/compose.yaml"))

    assert info.value.status_code == 429
    assert classify(info.value, billing_method="plan") is ErrorClass.RATE_LIMIT_PLAN
    assert fake_relay.instances[0].stopped


def test_relay_error_result_raises(fake_relay: type[_FakeRelayClient]) -> None:
    fake_relay.events = [ResultEvent(text="boom", is_error=True), EndEvent()]

    with pytest.raises(_SDKRuntimeError, match="boom"):
        _run_scan_via_relay(_mk_spec(), compose_path=Path("/app/compose.yaml"))


def test_relay_timeout_propagates_and_stops_client(
    fake_relay: type[_FakeRelayClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    def stalled(self: _FakeRelayClient, spec: ScanJobSpec) -> Iterator[Event]:
        raise subprocess.TimeoutExpired(cmd=["sdk-relay"], timeout=60)

    monkeypatch.setattr(fake_relay, "submit", stalled)
    with pytest.raises(subprocess.TimeoutExpired):
        _run_scan_via_relay(_mk_spec(), compose_path=Path("/app/compose.yaml"))
    assert fake_relay.instances[0].stopped


# ---------------------------------------------------------------------------
# Worker spec construction and status handling through the relay
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="my-secret"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_launch_builds_scan_job_spec(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo(path="/repos/target")]
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan", mcp_host="10.0.0.5", mcp_port=9999),
    )
    handle = launcher.launch(**_default_launch_kwargs(base_path="/data/tally"))
    handle.result.result(timeout=5)

    spec = mock_run.call_args.args[0]
    assert spec.mcp_servers == {
        "tally": {
            "type": "http",
            "url": "http://host.docker.internal:9999/mcp",
            "headers": {"Authorization": "Bearer my-secret"},
        }
    }
    assert spec.allowed_tools == [
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "Task",
        "WebFetch",
        "mcp__tally__*",
    ]
    assert spec.cwd == "/repos/target"
    assert spec.timeout_seconds == 3600
    assert (
        mock_run.call_args.kwargs["compose_path"]
        == Path("/data/tally") / COMPOSE_RELATIVE_PATH
    )


def _launch_with_relay(
    fake_relay: type[_FakeRelayClient],
    events: list[Event],
    *,
    status_repo: MagicMock,
    sink: _CapturingScanSink,
) -> str:
    fake_relay.events = events
    with (
        patch(
            "application.scans.background_launcher._mint_bearer_token",
            return_value="tok",
        ),
        patch(
            "application.scans.background_launcher.load_active_repos",
            return_value=[_mk_repo()],
        ),
    ):
        launcher = ScanBackgroundLauncher(
            mcp_service=_mk_mcp_service(),
            availability=_mk_availability(oauth_available=True, api_key_available=True),
            config=_mk_config(default_billing="plan"),
            scan_phase_repo=MagicMock(),
            scan_event_sink=sink,
            scan_run_status_repo=status_repo,
        )
        return launcher.launch(**_default_launch_kwargs()).result.result(timeout=5)


def test_relay_happy_path_writes_no_status(
    fake_relay: type[_FakeRelayClient],
) -> None:
    status_repo = MagicMock()
    sink = _CapturingScanSink()

    outcome = _launch_with_relay(
        fake_relay,
        [ResultEvent(text="ok", is_error=False), EndEvent()],
        status_repo=status_repo,
        sink=sink,
    )

    assert outcome == "done"
    status_repo.set_status_if_in.assert_not_called()
    assert sink.events == []


def test_relay_rate_limit_marks_run_and_emits_event(
    fake_relay: type[_FakeRelayClient],
) -> None:
    from domain.pipeline.scan_events import RunRateLimited

    status_repo = MagicMock()
    sink = _CapturingScanSink()

    outcome = _launch_with_relay(
        fake_relay,
        [ErrorEvent(status_code=429, subtype="rate_limit", message="x"), EndEvent()],
        status_repo=status_repo,
        sink=sink,
    )

    assert outcome == "terminated"
    status_repo.set_status_if_in.assert_called_once_with(
        1, "rate_limited", allowed_current=("queued", "running")
    )
    assert [type(e) for e in sink.events] == [RunRateLimited]


def test_relay_auth_failure_marks_run_failed_without_rate_limit_event(
    fake_relay: type[_FakeRelayClient],
) -> None:
    status_repo = MagicMock()
    sink = _CapturingScanSink()

    outcome = _launch_with_relay(
        fake_relay,
        [ErrorEvent(status_code=401, subtype="auth", message="x"), EndEvent()],
        status_repo=status_repo,
        sink=sink,
    )

    assert outcome == "terminated"
    status_repo.set_status_if_in.assert_called_once_with(
        1, "failed", allowed_current=("queued", "running")
    )
    assert sink.events == []


def test_relay_cancel_race_does_not_retry_status_write(
    fake_relay: type[_FakeRelayClient],
) -> None:
    status_repo = MagicMock()
    status_repo.set_status_if_in.return_value = False

    outcome = _launch_with_relay(
        fake_relay,
        [ErrorEvent(status_code=401, subtype="auth", message="x"), EndEvent()],
        status_repo=status_repo,
        sink=_CapturingScanSink(),
    )

    assert outcome == "terminated"
    status_repo.set_status_if_in.assert_called_once()
    status_repo.set_status.assert_not_called()


# ---------------------------------------------------------------------------
# _mint_bearer_token
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_mint_called_with_run_id_and_base_path(
    _mock_run: MagicMock,
    mock_repos: MagicMock,
    mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs(base_path="/data/tally"))
    handle.result.result(timeout=5)

    mock_mint.assert_called_once_with(1, base_path=Path("/data/tally"))


# ---------------------------------------------------------------------------
# mark_in_progress_failed cleanup port wiring
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_launcher_calls_mark_in_progress_failed_with_error_class(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    """Non-None scan_phase_repo receives mark_in_progress_failed on crash."""
    err = RuntimeError("something broke")
    mock_run.side_effect = err
    mock_repos.return_value = [_mk_repo()]
    scan_phase_repo = MagicMock()
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
        scan_phase_repo=scan_phase_repo,
    )
    handle = launcher.launch(**_default_launch_kwargs())
    result = handle.result.result(timeout=5)
    assert result == "terminated"

    scan_phase_repo.mark_in_progress_failed.assert_called_once()
    call_kwargs = scan_phase_repo.mark_in_progress_failed.call_args.kwargs
    assert call_kwargs["run_id"] == 1
    assert isinstance(call_kwargs["error_class"], str)


# ---------------------------------------------------------------------------
# RunRateLimited event emission
# ---------------------------------------------------------------------------


class _CapturingScanSink:
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event: object) -> None:
        self.events.append(event)


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_worker_emits_run_rate_limited_on_rate_limit_error_class(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    from domain.pipeline.scan_events import RunRateLimited

    err = RuntimeError("rate limit exceeded")
    err.status_code = 429  # type: ignore[attr-defined]
    mock_run.side_effect = err
    mock_repos.return_value = [_mk_repo()]
    sink = _CapturingScanSink()
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
        scan_phase_repo=MagicMock(),
        scan_event_sink=sink,
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    rl_events = [e for e in sink.events if isinstance(e, RunRateLimited)]
    assert len(rl_events) == 1
    assert rl_events[0].usage_pool == "plan"
    assert rl_events[0].run_id == 1
    assert rl_events[0].message == "usage pool plan exhausted"


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_worker_does_not_emit_run_rate_limited_on_other_error_classes(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    from domain.pipeline.scan_events import RunRateLimited

    err = RuntimeError("unknown failure")
    mock_run.side_effect = err
    mock_repos.return_value = [_mk_repo()]
    sink = _CapturingScanSink()
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
        scan_phase_repo=MagicMock(),
        scan_event_sink=sink,
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    rl_events = [e for e in sink.events if isinstance(e, RunRateLimited)]
    assert len(rl_events) == 0


# ---------------------------------------------------------------------------
# ScanRunStatusPort wiring
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_worker_marks_run_rate_limited_on_rate_limit_error(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    err = RuntimeError("rate limit exceeded")
    err.status_code = 429  # type: ignore[attr-defined]
    mock_run.side_effect = err
    mock_repos.return_value = [_mk_repo()]
    status_repo = MagicMock()
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
        scan_phase_repo=MagicMock(),
        scan_run_status_repo=status_repo,
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    status_repo.set_status_if_in.assert_called_once_with(
        1, "rate_limited", allowed_current=("queued", "running")
    )


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_scan_via_relay")
def test_worker_marks_run_failed_on_unknown_error(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_run.side_effect = RuntimeError("unknown failure")
    mock_repos.return_value = [_mk_repo()]
    status_repo = MagicMock()
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
        scan_phase_repo=MagicMock(),
        scan_run_status_repo=status_repo,
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    status_repo.set_status_if_in.assert_called_once_with(
        1, "failed", allowed_current=("queued", "running")
    )

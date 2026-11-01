"""Tests for ScanBackgroundLauncher orchestration and _run_sdk_skill wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.anthropic.mode_availability import BackgroundModeAvailability
from application.scans.background_launcher import (
    ScanBackgroundLauncher,
    ScanConfigurationError,
    _build_prompt,
    _run_sdk_skill,
)


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
@patch("application.scans.background_launcher._run_sdk_skill")
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
@patch("application.scans.background_launcher._run_sdk_skill")
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

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["cwd"] == "/repos/target"


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
def test_launch_mcp_url_includes_configured_host_and_port(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan", mcp_host="10.0.0.5", mcp_port=9999),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["mcp_server_url"] == "http://10.0.0.5:9999/mcp"


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="my-secret"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
def test_launch_bearer_token_passed_to_skill(
    mock_run: MagicMock,
    mock_repos: MagicMock,
    _mock_mint: MagicMock,
) -> None:
    mock_repos.return_value = [_mk_repo()]
    launcher = ScanBackgroundLauncher(
        mcp_service=_mk_mcp_service(),
        availability=_mk_availability(oauth_available=True, api_key_available=True),
        config=_mk_config(default_billing="plan"),
    )
    handle = launcher.launch(**_default_launch_kwargs())
    handle.result.result(timeout=5)

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["mcp_bearer_token"] == "my-secret"


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
@patch("application.scans.background_launcher._run_sdk_skill")
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
@patch("application.scans.background_launcher._run_sdk_skill")
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

    prompt = mock_run.call_args[0][0]
    assert "Resume:" in prompt
    assert "discovery" in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
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

    prompt = mock_run.call_args[0][0]
    assert "Resume:" in prompt
    assert "discovery" in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
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

    prompt = mock_run.call_args[0][0]
    assert "Resume:" not in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
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

    prompt = mock_run.call_args[0][0]
    assert "Resume:" not in prompt


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
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
# _run_sdk_skill SDK wiring tests
# ---------------------------------------------------------------------------


class TestRunSdkSkillWiring:
    """Verify _run_sdk_skill wires ClaudeAgentOptions correctly."""

    @staticmethod
    def _make_sdk_mocks() -> tuple[MagicMock, dict[str, Any]]:
        sdk = MagicMock()
        captured: dict[str, Any] = {}

        class FakeAssistantMessage:
            pass

        class FakeTextBlock:
            pass

        class FakeResultMessage:
            def __init__(self) -> None:
                self.is_error = False

        class FakeClaudeAgentOptions:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        sdk.AssistantMessage = FakeAssistantMessage
        sdk.TextBlock = FakeTextBlock
        sdk.ResultMessage = FakeResultMessage
        sdk.ClaudeAgentOptions = FakeClaudeAgentOptions

        async def fake_query(prompt: str, options: object) -> object:  # noqa: ARG004
            yield FakeResultMessage()

        sdk.query = fake_query
        return sdk, captured

    @patch("application.scans.background_launcher.build_child_env")
    def test_plan_mode_env_omits_api_key(self, mock_build_env: MagicMock) -> None:
        mock_build_env.return_value = {"PATH": "/usr/bin"}
        sdk, captured = self._make_sdk_mocks()

        sdk_types = MagicMock()
        sdk_types.McpHttpServerConfig = dict

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ):
            _run_sdk_skill(
                "Run /tally-scan-external",
                billing_method="plan",
                api_key_source=None,
                cwd="/tmp",
                model="x",
                mcp_server_url="http://127.0.0.1:8765/mcp",
                mcp_bearer_token="tok",
                timeout_seconds=60,
            )

        mock_build_env.assert_called_once()
        assert mock_build_env.call_args.kwargs["billing_method"] == "plan"
        assert "ANTHROPIC_API_KEY" not in captured.get("env", {})

    @patch("application.scans.background_launcher.build_child_env")
    def test_api_mode_env_contains_api_key(self, mock_build_env: MagicMock) -> None:
        mock_build_env.return_value = {"ANTHROPIC_API_KEY": "sk-test"}
        sdk, captured = self._make_sdk_mocks()

        sdk_types = MagicMock()
        sdk_types.McpHttpServerConfig = dict

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ):
            _run_sdk_skill(
                "Run /tally-scan-external",
                billing_method="api",
                api_key_source="sk-test",
                cwd="/tmp",
                model="x",
                mcp_server_url="http://127.0.0.1:8765/mcp",
                mcp_bearer_token="tok",
                timeout_seconds=60,
            )

        assert mock_build_env.call_args.kwargs["billing_method"] == "api"
        assert mock_build_env.call_args.kwargs["api_key_source"] == "sk-test"
        env = captured.get("env", {})
        assert env.get("ANTHROPIC_API_KEY") == "sk-test"

    @patch("application.scans.background_launcher.build_child_env")
    def test_mcp_server_url_and_bearer_token(self, mock_build_env: MagicMock) -> None:
        mock_build_env.return_value = {}
        sdk, captured = self._make_sdk_mocks()

        sdk_types = MagicMock()
        sdk_types.McpHttpServerConfig = dict

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ):
            _run_sdk_skill(
                "Run /tally-scan-external",
                billing_method="plan",
                api_key_source=None,
                cwd="/repos/app",
                model="x",
                mcp_server_url="http://10.0.0.1:9999/mcp",
                mcp_bearer_token="secret-tok",
                timeout_seconds=60,
            )

        mcp_servers = captured.get("mcp_servers", {})
        assert "tally" in mcp_servers
        tally_cfg = mcp_servers["tally"]
        assert tally_cfg["url"] == "http://10.0.0.1:9999/mcp"
        assert tally_cfg["headers"]["Authorization"] == "Bearer secret-tok"

    @patch("application.scans.background_launcher.build_child_env")
    def test_cwd_passed_to_options(self, mock_build_env: MagicMock) -> None:
        mock_build_env.return_value = {}
        sdk, captured = self._make_sdk_mocks()

        sdk_types = MagicMock()
        sdk_types.McpHttpServerConfig = dict

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ):
            _run_sdk_skill(
                "Run /tally-scan-external",
                billing_method="plan",
                api_key_source=None,
                cwd="/repos/my-project",
                model="x",
                mcp_server_url="http://127.0.0.1:8765/mcp",
                mcp_bearer_token="tok",
                timeout_seconds=60,
            )

        assert captured["cwd"] == "/repos/my-project"


# ---------------------------------------------------------------------------
# Error classification and timeout
# ---------------------------------------------------------------------------


@patch("application.scans.background_launcher.build_child_env")
def test_sdk_result_error_429_raises_with_status_code(
    mock_build_env: MagicMock,
) -> None:
    """ResultMessage(is_error=True, api_error_status=429) raises _SDKRuntimeError."""
    mock_build_env.return_value = {}
    sdk = MagicMock()

    class FakeAssistantMessage:
        pass

    class FakeTextBlock:
        pass

    class FakeResultMessage:
        def __init__(
            self, *, is_error: bool = False, api_error_status: int | None = None
        ) -> None:
            self.is_error = is_error
            self.api_error_status = api_error_status
            self.status_code = None
            self.subtype = "error"
            self.result = "rate limited"

    class FakeOptions:
        def __init__(self, **kwargs: object) -> None:
            pass

    sdk.AssistantMessage = FakeAssistantMessage
    sdk.TextBlock = FakeTextBlock
    sdk.ResultMessage = FakeResultMessage
    sdk.ClaudeAgentOptions = FakeOptions

    async def fake_query(prompt: str, options: object) -> object:  # noqa: ARG001
        yield FakeResultMessage(is_error=True, api_error_status=429)

    sdk.query = fake_query

    sdk_types = MagicMock()
    sdk_types.McpHttpServerConfig = dict

    from application.scans.background_launcher import _SDKRuntimeError

    with (
        patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ),
        pytest.raises(_SDKRuntimeError) as info,
    ):
        _run_sdk_skill(
            "prompt",
            billing_method="plan",
            api_key_source=None,
            cwd="/tmp",
            model="x",
            mcp_server_url="http://127.0.0.1:8765/mcp",
            mcp_bearer_token="tok",
            timeout_seconds=60,
        )

    assert info.value.status_code == 429

    # Verify the classifier maps this to RATE_LIMIT_PLAN
    from infrastructure.anthropic.error_classifier import (
        ErrorClass,
    )
    from infrastructure.anthropic.error_classifier import (
        classify as _classify,
    )

    kind = _classify(info.value, billing_method="plan")
    assert kind is ErrorClass.RATE_LIMIT_PLAN


@patch("application.scans.background_launcher.build_child_env")
def test_timeout_raises_timeout_expired(mock_build_env: MagicMock) -> None:
    """asyncio timeout surfaces as subprocess.TimeoutExpired."""
    mock_build_env.return_value = {}
    sdk = MagicMock()

    class FakeAssistantMessage:
        pass

    class FakeTextBlock:
        pass

    class FakeResultMessage:
        def __init__(self) -> None:
            self.is_error = False

    class FakeOptions:
        def __init__(self, **kwargs: object) -> None:
            pass

    sdk.AssistantMessage = FakeAssistantMessage
    sdk.TextBlock = FakeTextBlock
    sdk.ResultMessage = FakeResultMessage
    sdk.ClaudeAgentOptions = FakeOptions

    import asyncio as _asyncio

    async def hanging_query(prompt: str, options: object) -> object:  # noqa: ARG001
        await _asyncio.sleep(999)
        yield FakeResultMessage()  # pragma: no cover

    sdk.query = hanging_query

    sdk_types = MagicMock()
    sdk_types.McpHttpServerConfig = dict

    with (
        patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ),
        pytest.raises(subprocess.TimeoutExpired) as info,
    ):
        _run_sdk_skill(
            "prompt",
            billing_method="plan",
            api_key_source=None,
            cwd="/tmp",
            model="x",
            mcp_server_url="http://127.0.0.1:8765/mcp",
            mcp_bearer_token="tok",
            timeout_seconds=1,
        )

    assert info.value.timeout == 1


# ---------------------------------------------------------------------------
# _mint_bearer_token
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
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
# asyncio.TimeoutError identity (Python 3.10 compatibility)
# ---------------------------------------------------------------------------


@patch("application.scans.background_launcher.build_child_env")
def test_timeout_error_translated_to_timeout_expired(
    mock_build_env: MagicMock,
) -> None:
    """TimeoutError from asyncio.wait_for surfaces as subprocess.TimeoutExpired."""
    mock_build_env.return_value = {}
    sdk = MagicMock()

    class FakeOptions:
        def __init__(self, **kwargs: object) -> None:
            pass

    sdk.AssistantMessage = type("Msg", (), {})
    sdk.TextBlock = type("TB", (), {})
    sdk.ResultMessage = type("RM", (), {"is_error": False})
    sdk.ClaudeAgentOptions = FakeOptions

    async def timeout_query(prompt: str, options: object) -> object:  # noqa: ARG001
        raise TimeoutError
        yield  # make it an async generator  # pragma: no cover

    sdk.query = timeout_query

    sdk_types = MagicMock()
    sdk_types.McpHttpServerConfig = dict

    with (
        patch.dict(
            "sys.modules",
            {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
        ),
        pytest.raises(subprocess.TimeoutExpired) as info,
    ):
        _run_sdk_skill(
            "prompt",
            billing_method="plan",
            api_key_source=None,
            cwd="/tmp",
            model="x",
            mcp_server_url="http://127.0.0.1:8765/mcp",
            mcp_bearer_token="tok",
            timeout_seconds=30,
        )

    assert info.value.timeout == 30


# ---------------------------------------------------------------------------
# Tool allowlist
# ---------------------------------------------------------------------------


@patch("application.scans.background_launcher.build_child_env")
def test_allowed_tools_restricted_to_scan_set(mock_build_env: MagicMock) -> None:
    """ClaudeAgentOptions receives the restricted tool allowlist."""
    mock_build_env.return_value = {}
    sdk, captured = TestRunSdkSkillWiring._make_sdk_mocks()

    sdk_types = MagicMock()
    sdk_types.McpHttpServerConfig = dict

    with patch.dict(
        "sys.modules",
        {"claude_agent_sdk": sdk, "claude_agent_sdk.types": sdk_types},
    ):
        _run_sdk_skill(
            "Run /tally-scan-external",
            billing_method="plan",
            api_key_source=None,
            cwd="/tmp",
            model="x",
            mcp_server_url="http://127.0.0.1:8765/mcp",
            mcp_bearer_token="tok",
            timeout_seconds=60,
        )

    expected = ["Read", "Grep", "Glob", "Bash", "Task", "WebFetch", "mcp__tally__*"]
    assert captured["allowed_tools"] == expected
    assert "Write" not in captured["allowed_tools"]
    assert "Edit" not in captured["allowed_tools"]


# ---------------------------------------------------------------------------
# mark_in_progress_failed cleanup port wiring
# ---------------------------------------------------------------------------


@patch(
    "application.scans.background_launcher._mint_bearer_token", return_value="tok-abc"
)
@patch("application.scans.background_launcher.load_active_repos")
@patch("application.scans.background_launcher._run_sdk_skill")
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
@patch("application.scans.background_launcher._run_sdk_skill")
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
@patch("application.scans.background_launcher._run_sdk_skill")
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
@patch("application.scans.background_launcher._run_sdk_skill")
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
@patch("application.scans.background_launcher._run_sdk_skill")
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

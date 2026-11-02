import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.ports.triage_agent import TriageBackendUnavailable
from application.triage.prompts.output_instructions import STDOUT_OUTPUT_INSTRUCTION
from application.triage.prompts.triage_prompt import TriagePrompt
from domain.triage.verdict import Verdict
from infrastructure.anthropic import claude_sdk_triage_agent
from infrastructure.anthropic.claude_sdk_triage_agent import (
    AgentSDKTriageAgent,
    _SDKRuntimeError,
)
from infrastructure.anthropic.error_classifier import ErrorClass


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


@patch("infrastructure.anthropic.claude_sdk_triage_agent._run_sdk_once")
def test_run_triage_returns_parsed_verdict(mock_run: MagicMock) -> None:
    mock_run.return_value = _make_valid_verdict_json(1)
    agent = AgentSDKTriageAgent(
        billing_method="plan",
        api_key_source=None,
        model="claude-opus-4-6[1m]",
    )
    verdict = agent.run_triage(
        prompt=_fake_prompt("some triage prompt"),
        finding_id=1,
        timeout_seconds=300,
        cwd=Path("/tmp/repo"),
    )
    assert isinstance(verdict, Verdict)
    assert verdict.finding_id == 1


@patch("infrastructure.anthropic.claude_sdk_triage_agent._run_sdk_once")
def test_run_triage_classifies_rate_limit(mock_run: MagicMock) -> None:
    err = RuntimeError("Rate limit exceeded")
    err.status_code = 429  # type: ignore[attr-defined]
    mock_run.side_effect = err
    agent = AgentSDKTriageAgent(
        billing_method="plan",
        api_key_source=None,
        model="x",
    )

    with pytest.raises(TriageBackendUnavailable) as info:
        agent.run_triage(
            prompt=_fake_prompt(),
            finding_id=1,
            timeout_seconds=300,
            cwd=Path("/tmp/repo"),
        )
    assert info.value.error_class is ErrorClass.RATE_LIMIT_PLAN


def test_api_mode_requires_api_key_source() -> None:
    with pytest.raises(ValueError):
        AgentSDKTriageAgent(
            billing_method="api",
            api_key_source=None,
            model="x",
        )


class TestBuildChildEnvDelegation:
    """Verify _run_sdk_once delegates env construction to build_child_env."""

    @staticmethod
    def _make_sdk_mocks() -> tuple[MagicMock, dict[str, Any]]:
        """Return (sdk_module_mock, captured_options_dict)."""
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

        result_msg = FakeResultMessage()

        async def fake_query(prompt: str, options: object) -> object:  # noqa: ARG001
            yield result_msg

        sdk.query = fake_query
        return sdk, captured

    @patch("infrastructure.anthropic.claude_sdk_triage_agent.build_child_env")
    def test_plan_mode_env_omits_api_key(self, mock_build_env: MagicMock) -> None:
        """plan mode delegates to build_child_env, which strips the key."""
        mock_build_env.return_value = {"PATH": "/usr/bin"}
        sdk, captured = self._make_sdk_mocks()

        from infrastructure.anthropic.claude_sdk_triage_agent import (
            _run_sdk_once,
        )

        with patch.dict("sys.modules", {"claude_agent_sdk": sdk}):
            _run_sdk_once(
                instructions="trusted instructions",
                finding_data="untrusted finding",
                model="x",
                billing_method="plan",
                api_key_source=None,
                cwd="/tmp",
                timeout_seconds=60,
            )

        mock_build_env.assert_called_once()
        call_kwargs = mock_build_env.call_args
        assert call_kwargs.kwargs["billing_method"] == "plan"
        assert "ANTHROPIC_API_KEY" not in captured.get("env", {})

    @patch("infrastructure.anthropic.claude_sdk_triage_agent.build_child_env")
    def test_api_mode_env_contains_api_key(self, mock_build_env: MagicMock) -> None:
        """api mode delegates to build_child_env, which sets the key."""
        mock_build_env.return_value = {"ANTHROPIC_API_KEY": "sk-test"}
        sdk, captured = self._make_sdk_mocks()

        from infrastructure.anthropic.claude_sdk_triage_agent import (
            _run_sdk_once,
        )

        with patch.dict("sys.modules", {"claude_agent_sdk": sdk}):
            _run_sdk_once(
                instructions="trusted instructions",
                finding_data="untrusted finding",
                model="x",
                billing_method="api",
                api_key_source="sk-test",
                cwd="/tmp",
                timeout_seconds=60,
            )

        mock_build_env.assert_called_once()
        call_kwargs = mock_build_env.call_args
        assert call_kwargs.kwargs["billing_method"] == "api"
        assert call_kwargs.kwargs["api_key_source"] == "sk-test"
        env = captured.get("env", {})
        assert env.get("ANTHROPIC_API_KEY") == "sk-test"


@patch("infrastructure.anthropic.claude_sdk_triage_agent._run_sdk_once")
def test_sdk_runtime_error_with_status_classifies_as_rate_limit(
    mock_run: MagicMock,
) -> None:
    """_SDKRuntimeError(status_code=429) classifies as RATE_LIMIT_PLAN."""
    mock_run.side_effect = _SDKRuntimeError("overloaded", status_code=429)
    agent = AgentSDKTriageAgent(billing_method="plan", api_key_source=None, model="x")

    with pytest.raises(TriageBackendUnavailable) as info:
        agent.run_triage(
            prompt=_fake_prompt(),
            finding_id=1,
            timeout_seconds=300,
            cwd=Path("/tmp"),
        )
    assert info.value.error_class is ErrorClass.RATE_LIMIT_PLAN


@patch("infrastructure.anthropic.claude_sdk_triage_agent._run_sdk_once")
def test_timeout_raises_timeout_expired_not_unavailable(
    mock_run: MagicMock,
) -> None:
    """TimeoutError surfaces as subprocess.TimeoutExpired."""
    mock_run.side_effect = TimeoutError()
    agent = AgentSDKTriageAgent(billing_method="plan", api_key_source=None, model="x")

    with pytest.raises(subprocess.TimeoutExpired) as info:
        agent.run_triage(
            prompt=_fake_prompt(),
            finding_id=1,
            timeout_seconds=120,
            cwd=Path("/tmp"),
        )
    assert info.value.timeout == 120


def test_class_exposes_stdout_output_instruction() -> None:
    assert (
        claude_sdk_triage_agent.AgentSDKTriageAgent.OUTPUT_INSTRUCTION
        == STDOUT_OUTPUT_INSTRUCTION
    )

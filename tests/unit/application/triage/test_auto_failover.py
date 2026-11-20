"""Auto-failover: plan -> api on RATE_LIMIT_PLAN."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

from application.ports.triage_agent import TriageBackendUnavailable
from application.triage.factory import ResolvedTriageConfig
from application.triage.runner import TriageRunner
from domain.triage.entry import TriageBatchRow
from domain.triage.verdict import Verdict
from infrastructure.anthropic.error_classifier import ErrorClass


def _valid_verdict(finding_id: int = 100) -> Verdict:
    return Verdict(
        finding_id=finding_id,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="high",
        reasoning="test reasoning",
        remediation="fix it",
        attack_vector="GET /test",
        access_required="none",
        exploitation_complexity="low",
        user_interaction="none",
    )


_FINDING_DATA = {
    "id": 100,
    "tool": "semgrep",
    "repo": "testrepo",
    "file": "test.py",
    "line_start": 1,
    "severity": "high",
    "rule_id": "test-rule",
    "description": "Test finding",
    "cwe": "CWE-79",
    "code_snippet": "x = input()",
    "risk_type": "injection",
    "owasp": "A1",
}


def _make_batch_row() -> TriageBatchRow:
    return TriageBatchRow(
        id=1,
        run_id=1,
        finding_ids=[100],
        batch_data=[_FINDING_DATA],
        status="in_progress",
        run_attempts=1,
        created_at="2024-01-01T00:00:00",
        started_at="2024-01-01T00:00:01",
        completed_at=None,
        execution_id=1,
    )


@contextmanager
def _temp_app_root():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _make_runner(
    factory: MagicMock,
    *,
    enable_auto_failover: bool = False,
    api_key_available: bool = False,
) -> TriageRunner:
    initial_agent = factory.create()

    @contextmanager
    def _fake_prepare(**_kw):
        yield MagicMock(cwd=Path("/tmp"))

    initial_agent.prepare_session = MagicMock(side_effect=_fake_prepare)

    run_repo = MagicMock()
    run_repo.latest_run_id.return_value = 1

    triage_repo = MagicMock()
    triage_repo.claim_batch.side_effect = [_make_batch_row(), None]
    triage_repo.start_failover_execution.return_value = (99, 2)

    tool_obj = MagicMock(skip=False, scan_segment="sast")
    tool_registry = MagicMock()
    tool_registry.get_tool.return_value = tool_obj

    finding_repo = MagicMock()

    resolved_config = ResolvedTriageConfig(
        provider_name="claude_sdk",
        base_url="",
        model="test-model",
        timeout_seconds=30,
        retry_count=0,
        debug=False,
        billing_method="plan",
        api_key_source="sk-test" if api_key_available else None,
        auto_failover=enable_auto_failover,
    )

    with _temp_app_root() as app_root:
        runner = TriageRunner(
            project="test-project",
            run_repo=run_repo,
            triage_repo=triage_repo,
            audit_repo=None,
            app_root=app_root,
            registry=MagicMock(),
            event_sink=MagicMock(),
            triage_backend=initial_agent,
            session_timeout_seconds=30,
            retry_count=0,
            tool_registry=tool_registry,
            finding_repo=finding_repo,
            triage_provider="anthropic",
            billing_method="plan",
            agent_factory=factory,
            resolved_config=resolved_config,
            enable_auto_failover=enable_auto_failover,
            api_key_available=api_key_available,
        )
        runner.batch = MagicMock(return_value=(1, 1))
        return runner


def test_plan_rate_limit_triggers_api_retry_when_failover_enabled() -> None:
    plan_agent = MagicMock()
    plan_agent.run_triage.side_effect = TriageBackendUnavailable(
        "plan rate limit", error_class=ErrorClass.RATE_LIMIT_PLAN
    )
    api_agent = MagicMock()
    api_agent.run_triage.return_value = _valid_verdict()

    factory = MagicMock()
    factory.create.side_effect = [plan_agent, api_agent]

    runner = _make_runner(factory, enable_auto_failover=True, api_key_available=True)
    runner.run()

    assert plan_agent.run_triage.called
    assert api_agent.run_triage.called


def test_plan_rate_limit_aborts_when_failover_disabled() -> None:
    plan_agent = MagicMock()
    plan_agent.run_triage.side_effect = TriageBackendUnavailable(
        "plan rate limit", error_class=ErrorClass.RATE_LIMIT_PLAN
    )

    factory = MagicMock()
    factory.create.return_value = plan_agent

    runner = _make_runner(factory, enable_auto_failover=False)
    runner.run()

    assert runner.result is not None
    assert runner.result.status == "rate_limited"


def test_api_rate_limit_after_failover_aborts() -> None:
    plan_agent = MagicMock()
    plan_agent.run_triage.side_effect = TriageBackendUnavailable(
        "plan rate limit", error_class=ErrorClass.RATE_LIMIT_PLAN
    )
    api_agent = MagicMock()
    api_agent.run_triage.side_effect = TriageBackendUnavailable(
        "api rate limit", error_class=ErrorClass.RATE_LIMIT_API
    )

    factory = MagicMock()
    factory.create.side_effect = [plan_agent, api_agent]

    runner = _make_runner(factory, enable_auto_failover=True, api_key_available=True)
    runner.run()

    assert runner.result is not None
    assert runner.result.status == "rate_limited"
    assert runner.result.last_error_class == ErrorClass.RATE_LIMIT_API.value


def test_failover_calls_start_failover_execution_and_completes() -> None:
    """After plan rate limit, the repo is called with start_failover_execution
    for the claimed batch, and subsequent complete_batch targets the new execution.
    """
    plan_agent = MagicMock()
    plan_agent.run_triage.side_effect = TriageBackendUnavailable(
        "plan rate limit", error_class=ErrorClass.RATE_LIMIT_PLAN
    )
    api_agent = MagicMock()
    api_agent.run_triage.return_value = _valid_verdict()

    factory = MagicMock()
    factory.create.side_effect = [plan_agent, api_agent]

    runner = _make_runner(factory, enable_auto_failover=True, api_key_available=True)
    triage_repo = cast(MagicMock, runner._triage_repo)
    triage_repo.start_failover_execution.return_value = (99, 2)

    runner.run()

    triage_repo.start_failover_execution.assert_called_once_with(1, "api")
    triage_repo.complete_batch.assert_called_once_with(1, "completed")


def test_api_billing_does_not_failover_back_to_plan() -> None:
    """Automatic failover only runs plan -> api, never api -> plan."""
    api_agent = MagicMock()
    api_agent.run_triage.side_effect = TriageBackendUnavailable(
        "api rate limit", error_class=ErrorClass.RATE_LIMIT_API
    )

    factory = MagicMock()
    factory.create.return_value = api_agent

    runner = _make_runner(factory, enable_auto_failover=True, api_key_available=True)
    # Override billing to api so we're already on api
    runner._billing_method = "api"
    runner.run()

    assert runner.result is not None
    assert runner.result.status == "rate_limited"
    # Factory should not have been called again for a second agent
    assert factory.create.call_count == 1

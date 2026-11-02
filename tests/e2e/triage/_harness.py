"""Test harness for faking the Claude Agent SDK triage call."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from infrastructure.anthropic.claude_sdk_triage_agent import _SDKRuntimeError


@dataclass
class _ScriptedCall:
    kind: str  # "raise" | "return_verdict"
    exc: Exception | None = None
    verdict_text: str | None = None


@dataclass
class FakeSdkController:
    """Scripts outcomes for successive relay submit calls.

    Tracks the ordered list of scripted outcomes and the real call index.
    The active() context manager monkeypatches the relay submit in-place and
    restores it on exit.
    """

    _script: list[_ScriptedCall] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def on_call(self, n: int) -> _CallBuilder:
        """Return a builder that scripts call index *n* (1-based)."""
        while len(self._script) < n:
            self._script.append(_ScriptedCall(kind="return_verdict"))
        return _CallBuilder(controller=self, index=n - 1)

    @contextmanager
    def active(self) -> Iterator[FakeSdkController]:
        from infrastructure.anthropic.claude_sdk_triage_agent import (
            AgentSDKTriageAgent,
        )
        from infrastructure.anthropic.sdk_relay.client import SDKRelayClient
        from infrastructure.anthropic.sdk_relay.events import (
            EndEvent,
            ErrorEvent,
            ResultEvent,
        )

        original_run_triage = AgentSDKTriageAgent.run_triage
        billing_method = {"current": ""}

        # The relay job spec carries no billing info, so capture it from the
        # adapter to keep the plan-to-api failover assertions meaningful.
        def run_triage_spy(
            agent: AgentSDKTriageAgent, *args: Any, **kwargs: Any
        ) -> Any:
            billing_method["current"] = agent._billing_method
            return original_run_triage(agent, *args, **kwargs)

        def fake_submit(client: SDKRelayClient, spec: Any) -> Iterator[Any]:
            self.calls.append(
                {
                    "instructions": spec.system_prompt,
                    "finding_data": spec.user_prompt,
                    "model": spec.model,
                    "billing_method": billing_method["current"],
                    "cwd": spec.cwd,
                    "timeout_seconds": spec.timeout_seconds,
                }
            )
            index = len(self.calls) - 1
            if index >= len(self._script):
                raise AssertionError(
                    f"FakeSdkController: unexpected call {index + 1},"
                    f" only {len(self._script)} outcomes scripted"
                )
            scripted = self._script[index]
            if scripted.kind == "raise":
                assert isinstance(scripted.exc, _SDKRuntimeError)
                return iter(
                    [
                        ErrorEvent(
                            status_code=scripted.exc.status_code,
                            subtype="api_error",
                            message=str(scripted.exc),
                        ),
                        EndEvent(),
                    ]
                )
            if scripted.verdict_text is None:
                raise AssertionError(
                    f"FakeSdkController: call {index + 1} not scripted;"
                    f" use on_call({index + 1}).return_valid_verdict(...)"
                )
            return iter(
                [ResultEvent(text=scripted.verdict_text, is_error=False), EndEvent()]
            )

        with (
            patch.object(AgentSDKTriageAgent, "run_triage", run_triage_spy),
            patch.object(SDKRelayClient, "submit", fake_submit),
            patch.object(SDKRelayClient, "start", lambda self: None),
            patch.object(SDKRelayClient, "stop", lambda self: None),
        ):
            yield self


@dataclass
class _CallBuilder:
    controller: FakeSdkController
    index: int

    def raise_rate_limit_plan(
        self,
        message: str = "Rate limit exceeded for your Claude plan",
    ) -> None:
        """Script a 429 that classifies as RATE_LIMIT_PLAN under plan billing."""
        self.controller._script[self.index] = _ScriptedCall(
            kind="raise",
            exc=_SDKRuntimeError(message, status_code=429),
        )

    def return_verdict_text(self, text: str) -> None:
        self.controller._script[self.index] = _ScriptedCall(
            kind="return_verdict",
            verdict_text=text,
        )

    def return_valid_verdict(self, finding_id: int) -> None:
        """Build a parseable verdict JSON for *finding_id*.

        Uses the minimal "potential / vulnerability" shape that satisfies
        parse_verdict validation without triggering contradiction checks.
        """
        payload = {
            "finding_id": finding_id,
            "confidence": "potential",
            "finding_type": "vulnerability",
            "severity": "medium",
            "reasoning": "fake harness verdict",
            "remediation": "n/a",
            "attack_vector": "GET /test",
            "access_required": "none",
            "exploitation_complexity": "low",
            "user_interaction": "none",
        }
        self.return_verdict_text(json.dumps(payload))

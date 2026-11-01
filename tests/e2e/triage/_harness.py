"""Test harness for faking the Claude Agent SDK triage call."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _ScriptedCall:
    kind: str  # "raise" | "return_verdict"
    exc: Exception | None = None
    verdict_text: str | None = None


@dataclass
class FakeSdkController:
    """Scripts outcomes for successive _run_sdk_once calls.

    Tracks the ordered list of scripted outcomes and the real call index.
    The active() context manager monkeypatches _run_sdk_once in-place and
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
        import infrastructure.anthropic.claude_sdk_triage_agent as adapter

        original = adapter._run_sdk_once

        def fake(
            instructions: str,
            finding_data: str,
            model: str,
            billing_method: str,
            api_key_source: str | None,
            cwd: str,
            timeout_seconds: int,
        ) -> str:
            self.calls.append(
                {
                    "instructions": instructions,
                    "finding_data": finding_data,
                    "model": model,
                    "billing_method": billing_method,
                    "api_key_source": api_key_source,
                    "cwd": cwd,
                    "timeout_seconds": timeout_seconds,
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
                assert scripted.exc is not None
                raise scripted.exc
            if scripted.verdict_text is None:
                raise AssertionError(
                    f"FakeSdkController: call {index + 1} not scripted;"
                    f" use on_call({index + 1}).return_valid_verdict(...)"
                )
            return scripted.verdict_text

        adapter._run_sdk_once = fake  # type: ignore[assignment]
        try:
            yield self
        finally:
            adapter._run_sdk_once = original  # type: ignore[assignment]


@dataclass
class _CallBuilder:
    controller: FakeSdkController
    index: int

    def raise_rate_limit_plan(
        self,
        message: str = "Rate limit exceeded for your Claude plan",
    ) -> None:
        """Script a 429 that classifies as RATE_LIMIT_PLAN under plan billing."""
        from infrastructure.anthropic.claude_sdk_triage_agent import (
            _SDKRuntimeError,
        )

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

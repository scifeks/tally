"""Test harness for faking the Claude Agent SDK scan session."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

import application.scans.background_launcher as bl
from application.mcp.ingest_service import McpIngestService
from application.scans.background_launcher import _SDKRuntimeError


@dataclass
class _ScriptedPhase:
    phase: str
    kind: str  # "complete" | "rate_limit_plan"


@dataclass
class FakeSkillRunner:
    """Scripts per-phase outcomes for successive _run_scan_via_relay calls.

    The fake extracts run_id from the prompt to avoid a race between
    route-response and daemon-thread start.
    """

    ingest_service: McpIngestService
    project_name: str
    _script: list[_ScriptedPhase] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        """Clear the script between launches so each call runs fresh."""
        self._script.clear()

    def on_phase(self, phase: str) -> _PhaseBuilder:
        return _PhaseBuilder(controller=self, phase=phase)

    @contextmanager
    def active(
        self, billing_method: Literal["plan", "api"] = "plan"
    ) -> Iterator[FakeSkillRunner]:
        original = bl._run_scan_via_relay

        # The job spec carries no billing method, so the test supplies the pool
        # the launch under test was started with.
        def fake(spec: Any, **kwargs: Any) -> None:
            prompt = spec.user_prompt
            self.calls.append({"prompt": prompt, "spec": spec, **kwargs})

            run_id = _extract_run_id(prompt)
            billing = billing_method

            for scripted in self._script:
                self.ingest_service.start_scan_phase(
                    project=self.project_name,
                    run_id=run_id,
                    phase=scripted.phase,
                    usage_pool=billing,
                )
                if scripted.kind == "complete":
                    self.ingest_service.mark_scan_phase_complete(
                        project=self.project_name,
                        run_id=run_id,
                        phase=scripted.phase,
                        status="completed",
                        usage_pool=billing,
                    )
                elif scripted.kind == "rate_limit_plan":
                    self.ingest_service.mark_scan_phase_complete(
                        project=self.project_name,
                        run_id=run_id,
                        phase=scripted.phase,
                        status="rate_limited",
                        usage_pool=billing,
                    )
                    raise _SDKRuntimeError("rate limit (plan)", status_code=429)

        bl._run_scan_via_relay = fake  # type: ignore[assignment]
        try:
            yield self
        finally:
            bl._run_scan_via_relay = original  # type: ignore[assignment]


def _extract_run_id(prompt: str) -> int:
    """Parse run_id from the prompt built by _build_prompt."""
    match = re.search(r"Run id: (\d+)", prompt)
    if not match:
        raise ValueError(f"Cannot extract run_id from prompt: {prompt!r}")
    return int(match.group(1))


@dataclass
class _PhaseBuilder:
    controller: FakeSkillRunner
    phase: str

    def mark_complete(self) -> None:
        self.controller._script.append(_ScriptedPhase(self.phase, "complete"))

    def raise_rate_limit_plan(self) -> None:
        self.controller._script.append(_ScriptedPhase(self.phase, "rate_limit_plan"))

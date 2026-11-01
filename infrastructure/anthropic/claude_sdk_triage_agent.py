"""Agent SDK adapter implementing OneshotTriageBackendPort.

Each run_triage call starts a fresh SDK session with its own context window.
The runner above batches findings; this adapter handles one finding per call.

Security debt (TAL-266): this runs on the host with permission_mode=bypassPermissions.
Bypass is required so non-interactive runs do not hang on tool-use prompts, but it
gives the SDK session full Bash/Write/Edit access on the host. The follow-up ticket
moves non-interactive SDK runs into a Docker sandbox with a typed-event output relay
back to the host.
"""

from __future__ import annotations

import asyncio
import os
import subprocess as _subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageBackendUnavailable,
)
from domain.triage.verdict import Verdict, parse_verdict
from infrastructure.anthropic.error_classifier import classify
from infrastructure.anthropic.subprocess_env import build_child_env

if TYPE_CHECKING:
    from collections.abc import Iterator


class _SDKRuntimeError(RuntimeError):
    """Carries status_code from SDK ResultMessage errors for the classifier."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _run_sdk_once(
    prompt: str,
    model: str,
    billing_method: Literal["plan", "api"],
    api_key_source: str | None,
    cwd: str,
    timeout_seconds: int,
) -> str:
    """Start one SDK session, send one prompt, return the final text output.

    Separated from the class so tests can monkeypatch it without caring
    about the SDK's async internals.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    env = build_child_env(
        billing_method=billing_method,
        api_key_source=api_key_source,
        base_env=os.environ,
    )

    options = ClaudeAgentOptions(
        model=model,
        cwd=cwd,
        permission_mode="bypassPermissions",
        env=env,
    )

    async def _go() -> str:
        final_text = ""
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        final_text += block.text
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    status = getattr(msg, "api_error_status", None) or getattr(
                        msg, "status_code", None
                    )
                    raise _SDKRuntimeError(
                        f"SDK query error (subtype={msg.subtype}): "
                        f"{msg.result or 'unknown'}",
                        status_code=status,
                    )
        return final_text

    return asyncio.run(asyncio.wait_for(_go(), timeout=timeout_seconds))


class AgentSDKTriageAgent:
    """One-shot triage adapter using the Claude Agent SDK."""

    def __init__(
        self,
        billing_method: Literal["plan", "api"],
        api_key_source: str | None,
        model: str,
    ) -> None:
        if billing_method == "api" and not api_key_source:
            raise ValueError("billing_method='api' requires an api_key_source.")
        self._billing_method: Literal["plan", "api"] = billing_method
        self._api_key_source = api_key_source
        self._model = model

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ) -> Iterator[PreparedTriageSession]:
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        try:
            raw = _run_sdk_once(
                prompt=prompt,
                model=self._model,
                billing_method=self._billing_method,
                api_key_source=self._api_key_source,
                cwd=str(cwd),
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError as exc:
            raise _subprocess.TimeoutExpired(
                cmd=["claude-agent-sdk"], timeout=timeout_seconds
            ) from exc
        except Exception as exc:
            kind = classify(exc, billing_method=self._billing_method)
            raise TriageBackendUnavailable(
                f"Agent SDK failed for finding {finding_id}: {exc}",
                error_class=kind,
            ) from exc
        return parse_verdict(raw, expected_finding_id=finding_id)

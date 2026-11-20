"""Agent SDK adapter driving the Docker-sandboxed sdk-runner via SDKRelayClient.

Each run_triage call submits one job to the long-lived relay process and
translates the typed event stream back into the exception shapes the error
classifier and verdict parser already consume.
"""

from __future__ import annotations

import atexit
import subprocess as _subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from application.ports.triage_agent import (
    PreparedTriageSession,
    TriageBackendUnavailable,
)
from application.triage.prompts.output_instructions import (
    STDOUT_OUTPUT_INSTRUCTION,
)
from domain.triage.verdict import Verdict, parse_verdict
from infrastructure.anthropic.error_classifier import ErrorClass, classify
from infrastructure.anthropic.sdk_relay.client import (
    SDKRelayClient,
    SDKRelayUnavailable,
)
from infrastructure.anthropic.sdk_relay.events import ErrorEvent, ResultEvent
from infrastructure.anthropic.sdk_relay.job_spec import TriageJobSpec

if TYPE_CHECKING:
    from collections.abc import Iterator

    from application.triage.prompts.triage_prompt import TriagePrompt


class _SDKRuntimeError(RuntimeError):
    """Carries status_code from relay errors for the classifier."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _start_client(client: SDKRelayClient) -> None:
    try:
        client.start()
    except SDKRelayUnavailable as exc:
        raise TriageBackendUnavailable(
            f"SDK relay failed to start: {exc}",
            error_class=ErrorClass.UNKNOWN,
        ) from exc


class AgentSDKTriageAgent:
    """One-shot triage adapter using the Claude Agent SDK inside a sandbox."""

    OUTPUT_INSTRUCTION: ClassVar[str] = STDOUT_OUTPUT_INSTRUCTION

    def __init__(
        self,
        billing_method: Literal["plan", "api"],
        api_key_source: str | None,
        model: str,
        compose_path: Path,
    ) -> None:
        if billing_method == "api" and not api_key_source:
            raise ValueError("billing_method='api' requires an api_key_source.")
        self._billing_method: Literal["plan", "api"] = billing_method
        self._api_key_source = api_key_source
        self._model = model
        self._compose_path = compose_path
        self._client: SDKRelayClient | None = None

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ) -> Iterator[PreparedTriageSession]:
        client = SDKRelayClient(
            compose_path=self._compose_path, service_name="sdk-sidecar"
        )
        _start_client(client)
        self._client = client
        try:
            yield PreparedTriageSession(cwd=app_root)
        finally:
            self._client = None
            client.stop()

    def run_triage(
        self,
        prompt: TriagePrompt,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        # Plan-to-api failover swaps in a fresh adapter mid-run without a
        # prepare_session call, so start the relay on first use. Nothing
        # else stops it, so tie its shutdown to interpreter exit.
        if self._client is None:
            client = SDKRelayClient(
                compose_path=self._compose_path, service_name="sdk-sidecar"
            )
            _start_client(client)
            atexit.register(client.stop)
            self._client = client

        # Instructions go in as the system prompt so injection in finding
        # content cannot override them.
        spec = TriageJobSpec(
            model=self._model,
            system_prompt=prompt.instructions,
            user_prompt=prompt.finding_data,
            allowed_tools=["Read", "Grep", "Glob", "Bash"],
            cwd=str(cwd),
            timeout_seconds=timeout_seconds,
        )

        final_text = ""
        try:
            for event in self._client.submit(spec):
                if isinstance(event, ResultEvent):
                    if event.is_error:
                        raise _SDKRuntimeError(f"relay result error: {event.text}")
                    final_text = event.text
                elif isinstance(event, ErrorEvent):
                    raise _SDKRuntimeError(
                        f"relay error (subtype={event.subtype}): {event.message}",
                        status_code=event.status_code,
                    )
        except _subprocess.TimeoutExpired:
            raise
        except SDKRelayUnavailable as exc:
            raise TriageBackendUnavailable(
                f"SDK relay unavailable for finding {finding_id}: {exc}",
                error_class=ErrorClass.UNKNOWN,
            ) from exc
        except Exception as exc:
            kind = classify(exc, billing_method=self._billing_method)
            raise TriageBackendUnavailable(
                f"Agent SDK failed for finding {finding_id}: {exc}",
                error_class=kind,
            ) from exc
        return parse_verdict(final_text, expected_finding_id=finding_id)

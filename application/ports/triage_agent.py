"""Ports for triage backends."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from application.triage.verdict import Verdict


class TriageBackendUnavailable(RuntimeError):
    """Backend transport is gone and further calls in this run will fail.

    Adapters raise this when their persistent process (relay, MCP host,
    etc.) has died. The runner catches it, aborts the whole triage run,
    and leaves remaining batches ``pending`` so a resume can retry them.
    """


@dataclass(frozen=True)
class TriageSessionResult:
    """Outcome of one triage-agent session.

    success=True when the agent completed normally with zero exit code.
    Timeouts and errors set success=False with error details.
    """

    success: bool
    returncode: int
    stderr: str
    error: str | None = None


@dataclass(frozen=True)
class PreparedTriageSession:
    """Carries backend state into a session."""

    cwd: Path


@runtime_checkable
class TriageAgentPort(Protocol):
    """Run one triage-agent session.

    Agents are CLI tools (e.g. Claude Code), hosted models, or other
    backends that consume the rendered triage prompt and write findings
    back through the MCP server. The port is agent-agnostic: implementations
    encapsulate the binary, transport, and any security policy required to
    invoke them safely.

    ``cwd`` is the working directory the adapter passes to its underlying
    process. Claude Code uses it to locate ``.mcp.json``; other agents may
    ignore it.
    """

    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult: ...


@runtime_checkable
class TriageSessionPreparerPort(Protocol):
    """Builds per-run backend state."""

    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ) -> AbstractContextManager[PreparedTriageSession]: ...


@runtime_checkable
class TriageBackendPort(TriageAgentPort, TriageSessionPreparerPort, Protocol):
    """Backend contract used by the runner."""


@runtime_checkable
class OneshotTriagePort(Protocol):
    """Run one finding through a one-shot triage agent."""

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict: ...


@runtime_checkable
class OneshotTriageBackendPort(OneshotTriagePort, TriageSessionPreparerPort, Protocol):
    """One-shot backend contract. Adapters implement this from 2.2."""

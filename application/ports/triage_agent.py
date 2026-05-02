"""TriageAgent port: runs one triage-agent session per call."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


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

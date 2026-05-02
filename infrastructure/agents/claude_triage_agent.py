"""ClaudeTriageAgent: concrete TriageAgentPort backed by the Claude Code CLI.

Owns the argv that invokes the ``claude`` binary plus the security policy
that pins the flag set. The application service hands over a rendered prompt
and a timeout; this adapter handles the spawn, captures the result, and
translates timeouts and unexpected errors into a TriageSessionResult.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from application.ports.triage_agent import TriageAgentPort, TriageSessionResult

# SECURITY: --dangerously-skip-permissions and --disallowedTools must
# ALWAYS be present together. Removing or weakening either flag creates
# a privilege-escalation path. Rationale:
#
# 1. --dangerously-skip-permissions is required because the MCP server
#    startup otherwise triggers interactive permission prompts that
#    cannot be answered in a non-interactive subprocess.
#
# 2. --disallowedTools is the compensating control that prevents Claude
#    from using any tool that directly modifies the filesystem or makes
#    network requests (Bash, Write, Edit, MultiEdit, WebFetch,
#    WebSearch). Without this list, --dangerously-skip-permissions
#    would grant the Claude subprocess full filesystem and network
#    access under the operator's user identity.
#
# 3. The MCP permission manifest in .mcp.json
#    (allow: [get_findings_batch, update_findings_batch], deny: [*])
#    is a third layer of defense: the MCP server itself refuses calls
#    to any tool not explicitly allow-listed.
#
# 4. If --disallowedTools is removed or its tool list is shortened,
#    the Claude subprocess gains unrestricted filesystem write and
#    network access as the current user. That is a critical security
#    regression.
#
# NEVER remove --dangerously-skip-permissions or --disallowedTools,
# and NEVER reduce the set of tools listed in --disallowedTools.
_DISALLOWED_TOOLS = "Bash,Write,Edit,MultiEdit,WebFetch,WebSearch"


class ClaudeTriageAgent(TriageAgentPort):
    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult:
        try:
            completed = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--dangerously-skip-permissions",
                    "--disallowedTools",
                    _DISALLOWED_TOOLS,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(cwd),
            )
        except subprocess.TimeoutExpired:
            return TriageSessionResult(
                success=False,
                returncode=-1,
                stderr="",
                error=f"timed out after {timeout_seconds}s",
            )
        except Exception as exc:
            return TriageSessionResult(
                success=False,
                returncode=-1,
                stderr="",
                error=str(exc),
            )

        return TriageSessionResult(
            success=completed.returncode == 0,
            returncode=completed.returncode,
            stderr=completed.stderr or "",
        )

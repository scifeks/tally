"""Container-side SDK runner.

Reads one JSON job spec per line from stdin, invokes
claude_agent_sdk.query, and emits typed JSONL events on stdout. One
job's exception is confined; the loop reads the next job until EOF.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from typing import Any, TextIO

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from claude_agent_sdk.types import McpHttpServerConfig


def _emit(stdout: TextIO, obj: dict[str, Any]) -> None:
    stdout.write(json.dumps(obj) + "\n")
    stdout.flush()


def _make_options(spec: dict[str, Any]) -> ClaudeAgentOptions:
    kwargs: dict[str, Any] = {
        "model": spec["model"],
        "cwd": spec["cwd"],
        "permission_mode": "bypassPermissions",
        "env": dict(os.environ),
        "allowed_tools": list(spec.get("allowed_tools", [])),
    }
    system_prompt = spec.get("system_prompt")
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    mcp_servers = spec.get("mcp_servers") or {}
    if mcp_servers:
        kwargs["mcp_servers"] = {
            name: McpHttpServerConfig(
                type=cfg["type"],
                url=cfg["url"],
                headers=cfg.get("headers", {}),
            )
            for name, cfg in mcp_servers.items()
        }
    return ClaudeAgentOptions(**kwargs)


async def _run_job(spec: dict[str, Any], stdout: TextIO) -> None:
    # Lets the image be smoke-tested without Anthropic credentials.
    fake_response = os.environ.get("SDK_RUNNER_FAKE_RESPONSE")
    if fake_response:
        _emit(stdout, {"type": "result", "text": fake_response, "is_error": False})
        return
    options = _make_options(spec)
    timeout_s = int(spec["timeout_seconds"]) + 30

    async def _consume() -> None:
        async for msg in query(prompt=spec["user_prompt"], options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        _emit(stdout, {"type": "assistant_text", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        _emit(
                            stdout,
                            {
                                "type": "tool_use",
                                "name": getattr(block, "name", ""),
                                "tool_input": getattr(block, "input", {}) or {},
                            },
                        )
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    status = getattr(msg, "api_error_status", None) or getattr(
                        msg, "status_code", None
                    )
                    _emit(
                        stdout,
                        {
                            "type": "error",
                            "status_code": status,
                            "subtype": str(msg.subtype or "api_error"),
                            "message": str(msg.result or ""),
                        },
                    )
                else:
                    _emit(
                        stdout,
                        {
                            "type": "result",
                            "text": str(msg.result or ""),
                            "is_error": False,
                        },
                    )

    try:
        await asyncio.wait_for(_consume(), timeout=timeout_s)
    except TimeoutError:
        _emit(
            stdout,
            {
                "type": "error",
                "status_code": None,
                "subtype": "timeout",
                "message": f"in-container deadline ({timeout_s}s) elapsed",
            },
        )


def run_loop(stdin: TextIO, stdout: TextIO) -> None:
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            spec = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit(
                stdout,
                {
                    "type": "error",
                    "status_code": None,
                    "subtype": "bad_job",
                    "message": f"invalid job spec: {exc}",
                },
            )
            _emit(stdout, {"type": "end"})
            continue
        try:
            asyncio.run(_run_job(spec, stdout))
        # One job's failure must not end the long-lived exec session.
        except Exception as exc:
            _emit(
                stdout,
                {
                    "type": "error",
                    "status_code": getattr(exc, "status_code", None),
                    "subtype": type(exc).__name__,
                    "message": f"{exc}\n{traceback.format_exc()}",
                },
            )
        _emit(stdout, {"type": "end"})


def main() -> int:
    run_loop(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

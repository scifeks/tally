"""Shared helpers for tests/unit/mcp/."""

from __future__ import annotations

_next_id = 0


def _f(
    file: str = "src/a.py",
    severity: str = "medium",
    risk_type: str | None = "sqli",
    line_start: int = 1,
    tool: str = "semgrep",
    repo: str = "myrepo",
    **kwargs: object,
) -> dict:
    global _next_id
    _next_id += 1
    return {
        "id": _next_id,
        "tool": tool,
        "repo": repo,
        "file": file,
        "severity": severity,
        "risk_type": risk_type,
        "line_start": line_start,
        **kwargs,
    }

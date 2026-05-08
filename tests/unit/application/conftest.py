"""Shared helpers for tests/unit/application/."""

from __future__ import annotations

import pytest

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


@pytest.fixture(autouse=True)
def _reset_id_counter():
    """Reset global _next_id counter before each test to prevent bleed."""
    global _next_id
    _next_id = 0
    yield


@pytest.fixture()
def next_id():
    """Returns an incrementing callable, reset per test."""
    counter = {"v": 0}

    def _inc() -> int:
        counter["v"] += 1
        return counter["v"]

    return _inc

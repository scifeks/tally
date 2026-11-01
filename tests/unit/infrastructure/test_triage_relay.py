"""Tests for the triage-relay script's per-request protocol."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_RELAY = (
    Path(__file__).resolve().parents[3] / "docker" / "triage-agent" / "triage-relay.sh"
)

# Stands in for claude/opencode: echoes back the argv and stdin it received.
_ECHO_CMD = [
    sys.executable,
    "-c",
    "import json, sys; "
    "print(json.dumps({'args': sys.argv[1:], 'stdin': sys.stdin.read()}))",
]

_INSTRUCTIONS = 'Trusted rules.\nLine two with "quotes", $(whoami) and `ticks`.'
_DATA = "finding data\nsecond line"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _relay(relay_args: list[str], system: str, tmp_path: Path) -> dict[str, object]:
    request = f"30\n{_b64(system) if system else ''}\n{_b64(_DATA)}\n"
    completed = subprocess.run(
        ["bash", str(_RELAY), *relay_args, *_ECHO_CMD],
        input=request,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("relay_args", "system", "expected_extra_args"),
    [
        pytest.param(
            ["--system-prompt-flag", "--append-system-prompt"],
            _INSTRUCTIONS,
            ["--append-system-prompt", _INSTRUCTIONS],
            id="system-prompt-passed-verbatim-as-flag-value",
        ),
        pytest.param(
            ["--system-prompt-flag", "--append-system-prompt"],
            "",
            [],
            id="empty-system-line-adds-no-flag",
        ),
        pytest.param([], "", [], id="no-flag-configured-single-message"),
    ],
)
def test_relay_routes_system_prompt_and_data(
    relay_args: list[str],
    system: str,
    expected_extra_args: list[str],
    tmp_path: Path,
) -> None:
    response = _relay(relay_args, system, tmp_path)

    assert response["rc"] == 0
    echoed = json.loads(base64.b64decode(str(response["out"])))
    assert echoed["args"] == expected_extra_args
    assert echoed["stdin"] == _DATA


def test_relay_refuses_system_prompt_without_flag(tmp_path: Path) -> None:
    response = _relay([], _INSTRUCTIONS, tmp_path)

    assert response["rc"] == 2
    assert response["out"] == ""
    assert b"--system-prompt-flag" in base64.b64decode(str(response["err"]))

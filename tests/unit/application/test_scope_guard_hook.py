"""Tests for the scope-guard PreToolUse hook script.

Runs the bash script via subprocess with crafted JSON inputs
and asserts on exit codes. Requires jq on the test machine.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
_HOOK = _TALLY_ROOT / "docker" / "triage-agent" / "hooks" / "scope-guard.sh"

_skip_no_jq = pytest.mark.skipif(
    shutil.which("jq") is None,
    reason="jq not installed",
)

if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))


def _run_hook(tool_name: str, tool_input: dict) -> int:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    result = subprocess.run(
        ["bash", str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode


@_skip_no_jq
class TestReadScope:
    def test_allows_path_inside_repos(self) -> None:
        rc = _run_hook(
            "Read",
            {"file_path": "/workspace/repos/myrepo/src/app.py"},
        )
        assert rc == 0

    def test_blocks_path_outside_repos(self) -> None:
        rc = _run_hook(
            "Read",
            {"file_path": ("/home/agent/.claude/.credentials.json")},
        )
        assert rc == 2

    def test_blocks_etc_passwd(self) -> None:
        rc = _run_hook("Read", {"file_path": "/etc/passwd"})
        assert rc == 2

    def test_blocks_traversal_attempt(self) -> None:
        rc = _run_hook(
            "Read",
            {"file_path": ("/workspace/repos/evil/../../.claude/.credentials.json")},
        )
        assert rc == 2

    def test_blocks_relative_traversal(self) -> None:
        rc = _run_hook(
            "Read",
            {"file_path": "../etc/passwd"},
        )
        assert rc == 2

    def test_allows_relative_repo_path(self) -> None:
        rc = _run_hook(
            "Read",
            {"file_path": "repos/myrepo/file.py"},
        )
        assert rc == 0

    def test_allows_deeply_nested_repo_path(self) -> None:
        rc = _run_hook(
            "Read",
            {"file_path": ("/workspace/repos/app/src/main/java/App.java")},
        )
        assert rc == 0


@_skip_no_jq
class TestGrepScope:
    def test_allows_no_path_field(self) -> None:
        rc = _run_hook("Grep", {"pattern": "password"})
        assert rc == 0

    def test_blocks_absolute_path_outside_repos(self) -> None:
        rc = _run_hook(
            "Grep",
            {"pattern": "key", "path": "/home/agent"},
        )
        assert rc == 2

    def test_allows_path_inside_repos(self) -> None:
        rc = _run_hook(
            "Grep",
            {
                "pattern": "TODO",
                "path": "/workspace/repos/app",
            },
        )
        assert rc == 0

    def test_blocks_relative_path_outside_repos(
        self,
    ) -> None:
        rc = _run_hook(
            "Grep",
            {"pattern": "secret", "path": "../etc"},
        )
        assert rc == 2


@_skip_no_jq
class TestGlobScope:
    def test_allows_relative_pattern(self) -> None:
        rc = _run_hook("Glob", {"pattern": "**/*.py"})
        assert rc == 0

    def test_blocks_absolute_path_outside_repos(self) -> None:
        rc = _run_hook(
            "Glob",
            {
                "pattern": "*.json",
                "path": "/home/agent/.claude",
            },
        )
        assert rc == 2

    def test_blocks_absolute_pattern_outside_repos(
        self,
    ) -> None:
        rc = _run_hook("Glob", {"pattern": "/etc/**/*"})
        assert rc == 2

    def test_allows_absolute_pattern_inside_repos(
        self,
    ) -> None:
        rc = _run_hook(
            "Glob",
            {"pattern": "/workspace/repos/app/**/*.py"},
        )
        assert rc == 0


@_skip_no_jq
class TestOtherTools:
    def test_allows_unknown_tool(self) -> None:
        rc = _run_hook("Bash", {"command": "cat /etc/passwd"})
        assert rc == 0

    def test_allows_empty_tool_name(self) -> None:
        rc = _run_hook("", {})
        assert rc == 0

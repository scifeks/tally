"""E2E tests for clear, exit, quit, and unknown command handling."""

from __future__ import annotations

import json

import pexpect
import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.e2e


def test_clear_produces_no_error(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("clear")
    assert "error" not in output.lower()
    assert "traceback" not in output.lower()


def test_exit_prints_goodbye(tmp_path) -> None:
    harness = TallyHarness(base_path=tmp_path)
    harness.setup()
    (tmp_path / "config" / "commands.json").write_text(json.dumps({}))
    harness.spawn()
    harness.send("exit")
    harness.expect("Goodbye")
    assert harness.child is not None
    harness.child.expect(pexpect.EOF, timeout=10)
    assert not harness.child.isalive()
    harness.child = None


def test_quit_prints_goodbye(tmp_path) -> None:
    harness = TallyHarness(base_path=tmp_path)
    harness.setup()
    (tmp_path / "config" / "commands.json").write_text(json.dumps({}))
    harness.spawn()
    harness.send("quit")
    harness.expect("Goodbye")
    assert harness.child is not None
    harness.child.expect(pexpect.EOF, timeout=10)
    assert not harness.child.isalive()
    harness.child = None


def test_unknown_command_shows_error(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("foobar")
    assert "Unknown command" in output
    assert "foobar" in output
    assert "help" in output


def test_unknown_command_with_args(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("foobar baz qux")
    assert "Unknown command" in output
    assert "foobar" in output

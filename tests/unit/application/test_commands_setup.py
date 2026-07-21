"""Unit tests for commands_setup helpers (application.setup.commands_setup)."""

from __future__ import annotations

from unittest.mock import patch

from application.setup.commands_setup import (
    _has_metachar,
    _reject_metachar,
    find_local_binary,
)


class TestCommandsSetup:
    def test_find_local_binary_returns_path_when_found(self) -> None:
        with (
            patch(
                "application.setup.commands_setup._get_wrapper_meta",
                return_value={
                    "candidate_commands": ["semgrep"],
                    "tool_type": "repo",
                },
            ),
            patch(
                "application.setup.commands_setup.shutil.which",
                return_value="/usr/local/bin/semgrep",
            ),
        ):
            result = find_local_binary("semgrep")

        assert result == "/usr/local/bin/semgrep"

    def test_find_local_binary_returns_none_when_not_found(self) -> None:
        with (
            patch(
                "application.setup.commands_setup._get_wrapper_meta",
                return_value={
                    "candidate_commands": ["unknowntool"],
                    "tool_type": "repo",
                },
            ),
            patch(
                "application.setup.commands_setup.shutil.which",
                return_value=None,
            ),
        ):
            result = find_local_binary("unknowntool")

        assert result is None

    def test_has_metachar_true_for_semicolon(self) -> None:
        assert _has_metachar("foo;bar") is True

    def test_has_metachar_true_for_pipe(self) -> None:
        assert _has_metachar("foo|bar") is True

    def test_has_metachar_true_for_backtick(self) -> None:
        assert _has_metachar("foo`bar") is True

    def test_has_metachar_true_for_dollar(self) -> None:
        assert _has_metachar("echo $HOME") is True

    def test_has_metachar_false_for_clean_path(self) -> None:
        assert _has_metachar("/usr/local/bin/semgrep") is False

    def test_has_metachar_false_for_empty_string(self) -> None:
        assert _has_metachar("") is False


class TestRejectMetachar:
    def test_returns_true_and_prints_error(self, capsys) -> None:
        result = _reject_metachar("binary path", "cd && foo")
        assert result is True
        captured = capsys.readouterr()
        assert "shell metacharacters" in captured.out
        assert "cannot be saved" in captured.out

    def test_returns_false_for_clean_input(self) -> None:
        result = _reject_metachar("test", "/usr/bin/tool")
        assert result is False

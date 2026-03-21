"""Unit tests for sanitize_command (application.tools.executor)."""

from __future__ import annotations

import pytest

from application.tools.executor import sanitize_command


class TestSanitizeCommand:
    def test_clean_tokens_returned_unchanged(self) -> None:
        result = sanitize_command(["ls", "-la", "/tmp"])
        assert result == ["ls", "-la", "/tmp"]

    @pytest.mark.parametrize("token", ["&&", "||", ";", ">", ">>", "<", "<<", "|"])
    def test_operator_tokens_raise(self, token: str) -> None:
        with pytest.raises(ValueError):
            sanitize_command(["ls", token])

    @pytest.mark.parametrize(
        "token",
        [
            "foo;bar",
            "foo&bar",
            "foo|bar",
            "foo<bar",
            "foo>bar",
            "foo`bar",
            "foo$bar",
        ],
    )
    def test_metachar_in_token_raises(self, token: str) -> None:
        with pytest.raises(ValueError):
            sanitize_command(["ls", token])

    def test_empty_list_returns_empty(self) -> None:
        assert sanitize_command([]) == []

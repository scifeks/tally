"""Unit tests for UserPromptPort adapters."""

from __future__ import annotations

from unittest.mock import patch

from application.ports.user_prompt import UserPromptPort
from application.repl.adapters.rich_console_prompt import RichConsolePromptAdapter
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter


class TestNoApprovalPromptAdapter:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(NoApprovalPromptAdapter(), UserPromptPort)

    def test_confirm_always_returns_true(self) -> None:
        adapter = NoApprovalPromptAdapter()
        assert adapter.confirm("Destroy everything?") is True

    def test_confirm_ignores_default(self) -> None:
        adapter = NoApprovalPromptAdapter()
        assert adapter.confirm("Proceed?", default=False) is True

    def test_approve_all_remaining_is_noop(self) -> None:
        adapter = NoApprovalPromptAdapter()
        adapter.approve_all_remaining()  # must not raise


class TestRichConsolePromptAdapter:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(RichConsolePromptAdapter(), UserPromptPort)

    def test_confirm_yes(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="y"):
            assert adapter.confirm("Proceed?") is True

    def test_confirm_yes_uppercase(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="Y"):
            assert adapter.confirm("Proceed?") is True

    def test_confirm_yes_full_word(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="yes"):
            assert adapter.confirm("Proceed?") is True

    def test_confirm_no(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="n"):
            assert adapter.confirm("Proceed?") is False

    def test_confirm_empty_uses_default_false(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value=""):
            assert adapter.confirm("Proceed?", default=False) is False

    def test_confirm_empty_uses_default_true(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value=""):
            assert adapter.confirm("Proceed?", default=True) is True

    def test_confirm_eof_returns_false(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", side_effect=EOFError):
            assert adapter.confirm("Proceed?") is False

    def test_confirm_keyboard_interrupt_returns_false(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert adapter.confirm("Proceed?") is False

    def test_auto_approve_bypasses_input(self) -> None:
        adapter = RichConsolePromptAdapter()
        adapter._auto_approve = True
        with patch("builtins.input", side_effect=AssertionError("should not prompt")):
            assert adapter.confirm("Proceed?") is True

    def test_approve_all_remaining_sets_auto_approve_on_yes(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="y"):
            adapter.approve_all_remaining()
        assert adapter._auto_approve is True

    def test_approve_all_remaining_no_does_not_set_auto_approve(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="n"):
            adapter.approve_all_remaining()
        assert adapter._auto_approve is False

    def test_approve_all_remaining_eof_does_not_set_auto_approve(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", side_effect=EOFError):
            adapter.approve_all_remaining()
        assert adapter._auto_approve is False

    def test_approve_all_remaining_already_set_skips_prompt(self) -> None:
        adapter = RichConsolePromptAdapter()
        adapter._auto_approve = True
        with patch("builtins.input", side_effect=AssertionError("should not prompt")):
            adapter.approve_all_remaining()

    def test_auto_approve_persists_across_calls(self) -> None:
        adapter = RichConsolePromptAdapter()
        with patch("builtins.input", return_value="y"):
            adapter.approve_all_remaining()
        with patch("builtins.input", side_effect=AssertionError("should not prompt")):
            assert adapter.confirm("Anything?") is True
            assert adapter.confirm("Again?") is True

    def test_prompt_suffix_default_false(self) -> None:
        adapter = RichConsolePromptAdapter()
        captured: list[str] = []
        with patch("builtins.input", side_effect=lambda q: captured.append(q) or "n"):
            adapter.confirm("Run tool?", default=False)
        assert "[y/N]" in captured[0]

    def test_prompt_suffix_default_true(self) -> None:
        adapter = RichConsolePromptAdapter()
        captured: list[str] = []
        with patch("builtins.input", side_effect=lambda q: captured.append(q) or ""):
            adapter.confirm("Run tool?", default=True)
        assert "[Y/n]" in captured[0]

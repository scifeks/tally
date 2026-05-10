"""Unit tests for CLI adapter implementations."""

from __future__ import annotations

import pytest

from application.cli.adapters import CliProgressReporter, CliPromptAdapter


class TestCliPromptAdapterConfirm:
    def test_confirm_returns_true(self) -> None:
        adapter = CliPromptAdapter()
        result = adapter.confirm("Do you want to continue?")
        assert result is True

    @pytest.mark.parametrize("default", [True, False])
    def test_confirm_ignores_default_parameter(self, default: bool) -> None:
        adapter = CliPromptAdapter()
        result = adapter.confirm("Do you want to continue?", default=default)
        assert result is True

    def test_confirm_always_true_regardless_of_question(self) -> None:
        adapter = CliPromptAdapter()
        questions = [
            "Do you want to delete all findings?",
            "Continue with the operation?",
            "Is this correct?",
            "Proceed?",
        ]
        for question in questions:
            result = adapter.confirm(question)
            assert result is True


class TestCliPromptAdapterApproveAllRemaining:
    def test_approve_all_remaining_returns_none(self) -> None:
        adapter = CliPromptAdapter()
        result = adapter.approve_all_remaining()
        assert result is None

    def test_approve_all_remaining_does_not_raise(self) -> None:
        adapter = CliPromptAdapter()
        # Should not raise any exception
        adapter.approve_all_remaining()


class TestCliProgressReporter:
    def test_report_prints_message_to_stdout(self, capsys) -> None:
        reporter = CliProgressReporter()
        reporter.report("Processing findings...")
        captured = capsys.readouterr()
        assert "Processing findings..." in captured.out

    def test_report_prints_different_messages(self, capsys) -> None:
        reporter = CliProgressReporter()
        messages = [
            "Scanning repository...",
            "Analyzing code...",
            "Triaging results...",
        ]

        for message in messages:
            capsys.readouterr()  # Clear previous output
            reporter.report(message)
            captured = capsys.readouterr()
            assert message in captured.out

    def test_report_prints_multiline_message(self, capsys) -> None:
        reporter = CliProgressReporter()
        multiline = "Line 1\nLine 2\nLine 3"
        reporter.report(multiline)
        captured = capsys.readouterr()
        assert "Line 1" in captured.out
        assert "Line 2" in captured.out
        assert "Line 3" in captured.out

    def test_report_with_empty_message(self, capsys) -> None:
        reporter = CliProgressReporter()
        reporter.report("")
        captured = capsys.readouterr()
        # Empty string prints as a blank line
        assert captured.out == "\n"

    def test_report_multiple_times(self, capsys) -> None:
        reporter = CliProgressReporter()
        reporter.report("First message")
        reporter.report("Second message")
        reporter.report("Third message")
        captured = capsys.readouterr()
        assert "First message" in captured.out
        assert "Second message" in captured.out
        assert "Third message" in captured.out

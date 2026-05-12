"""Unit tests for ProgressReporter adapters."""

from __future__ import annotations

import pytest

from application.ports.progress_reporter import (
    NullProgressReporter,
    ProgressReporter,
)
from application.repl.adapters.stdout_progress_reporter import StdoutProgressReporter


class TestNullProgressReporter:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(NullProgressReporter(), ProgressReporter)

    def test_report_returns_none(self) -> None:
        assert NullProgressReporter().report("anything") is None

    def test_report_emits_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        NullProgressReporter().report("should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestStdoutProgressReporter:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(StdoutProgressReporter(), ProgressReporter)

    def test_report_writes_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        StdoutProgressReporter().report("hello world")
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"

    def test_different_messages_print_on_separate_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        r = StdoutProgressReporter()
        r.report("first message")
        r.report("second message")
        captured = capsys.readouterr()
        assert captured.out == "first message\nsecond message\n"

    def test_same_prefix_overwrites_previous_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        r = StdoutProgressReporter()
        r.report("    Enriching findings... 1/61")
        r.report("    Enriching findings... 2/61")
        captured = capsys.readouterr()
        assert "    Enriching findings... 1/61\n" in captured.out
        assert "\033[A\r\033[2K" in captured.out
        assert captured.out.endswith("    Enriching findings... 2/61\n")

    def test_overwrite_stops_when_prefix_changes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        r = StdoutProgressReporter()
        r.report("    Enriching findings... 1/61")
        r.report("    Enriching findings... 2/61")
        capsys.readouterr()
        r.report("    Enrichment complete. 2/61 enriched.")
        captured = capsys.readouterr()
        assert captured.out == ("    Enrichment complete. 2/61 enriched.\n")

    def test_empty_message_does_not_trigger_overwrite(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        r = StdoutProgressReporter()
        r.report("")
        r.report("")
        captured = capsys.readouterr()
        assert captured.out == "\n\n"

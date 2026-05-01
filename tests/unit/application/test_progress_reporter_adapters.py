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

"""Unit tests for ReportCommand (application.repl.commands.report)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.report import ReportCommand


@pytest.fixture()
def mock_repl() -> MagicMock:
    repl = MagicMock()
    repl.active_project = "test-project"
    repl.base_path = "/tmp/test"
    return repl


@pytest.fixture()
def cmd(mock_repl: MagicMock) -> ReportCommand:
    return ReportCommand(mock_repl)


class TestReportCommand:
    def test_flag_not_present_returns_none(self) -> None:
        result = ReportCommand._parse_value_flag(["--output", "out.md"], "--format")
        assert result == (None, ["--output", "out.md"])

    def test_flag_at_end_with_no_value_returns_none(self) -> None:
        result = ReportCommand._parse_value_flag(["--format"], "--format")
        assert result == (None, ["--format"])

    def test_valid_flag_pair_returns_value_and_remaining(self) -> None:
        result = ReportCommand._parse_value_flag(
            ["--format", "json", "--output", "x.json"], "--format"
        )
        assert result == ("json", ["--output", "x.json"])

    def test_unknown_format_prints_error_and_returns(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        cmd.execute("report", ["--format", "xml"])

        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "Unknown format" in printed

    def test_no_active_project_prints_warning_and_returns(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_repl.active_project = None
        cmd.execute("report", [])

        mock_repl.console.print.assert_called()

    def test_valid_call_invokes_generator_generate(
        self,
        cmd: ReportCommand,
        mock_repl: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        mock_rag = MagicMock()
        with (
            patch.object(ReportCommand, "_get_rag_engine", return_value=mock_rag),
            patch("application.reporting.generator.ReportGenerator") as mock_gen_cls,
        ):
            cmd.execute("report", [])

        mock_gen_cls.return_value.generate.assert_called_once()
        _, kwargs = mock_gen_cls.return_value.generate.call_args
        assert kwargs["output_format"] == "markdown"

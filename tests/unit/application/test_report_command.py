"""Unit tests for ReportCommand (application.repl.commands.report)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.report import ReportCommand
from application.reporting.resolver import SectionMissingError


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

    # ------------------------------------------------------------------
    # _parse_value_flag — equals form (Bugs 5 & 6)
    # ------------------------------------------------------------------

    def test_equals_form_extracts_value(self) -> None:
        result = ReportCommand._parse_value_flag(["--format=json"], "--format")
        assert result == ("json", [])

    def test_equals_form_leaves_other_args(self) -> None:
        result = ReportCommand._parse_value_flag(
            ["--format=html", "--output", "x.html"], "--format"
        )
        assert result == ("html", ["--output", "x.html"])

    def test_equals_form_output_flag(self) -> None:
        result = ReportCommand._parse_value_flag(
            ["--output=some/path.html"], "--output"
        )
        assert result == ("some/path.html", [])

    def test_space_form_still_works_after_fix(self) -> None:
        result = ReportCommand._parse_value_flag(
            ["--format", "json", "--output", "x.json"], "--format"
        )
        assert result == ("json", ["--output", "x.json"])

    def test_equals_truly_unknown_format_shows_error(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        cmd.execute("report", ["--format=docx"])
        printed = " ".join(str(c) for c in mock_repl.console.print.call_args_list)
        assert "Unknown format" in printed

    def test_format_pdf_delegates_to_assemble(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.return_value = MagicMock()
            mock_cls.return_value.render_pdf.return_value = b"%PDF"
            cmd.execute("report", ["--format=pdf"])
        mock_cls.assert_called_once()
        mock_cls.return_value.build_context.assert_called_once()
        mock_cls.return_value.render_pdf.assert_called_once()

    # ------------------------------------------------------------------
    # Bug 2 — SectionMissingError is shown in assemble and shell
    # ------------------------------------------------------------------

    def test_assemble_shows_section_missing_error(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.side_effect = SectionMissingError(
                "executive-summary"
            )
            cmd.execute("report", ["assemble"])
        printed = " ".join(str(c) for c in mock_repl.console.print.call_args_list)
        assert "Section missing" in printed

    def test_shell_shows_section_missing_error(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.side_effect = SectionMissingError(
                "risk-level"
            )
            cmd.execute("report", ["shell"])
        printed = " ".join(str(c) for c in mock_repl.console.print.call_args_list)
        assert "Section missing" in printed

    # ------------------------------------------------------------------
    # report draft — no-section generates all sections
    # ------------------------------------------------------------------

    def test_draft_no_section_calls_generate_for_every_section(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        from application.reporting.draft_runner import get_all_sections

        with patch("application.reporting.draft_runner.generate_draft") as mock_gen:
            cmd.execute("report", ["draft"])

        all_sections = get_all_sections()
        assert mock_gen.call_count == len(all_sections)
        called_sections = [c.kwargs["section"] for c in mock_gen.call_args_list]
        assert called_sections == all_sections

    def test_draft_with_section_calls_generate_once(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        with patch("application.reporting.draft_runner.generate_draft") as mock_gen:
            cmd.execute("report", ["draft", "risk-level"])

        assert mock_gen.call_count == 1
        assert mock_gen.call_args.kwargs["section"] == "risk-level"

    def test_draft_no_active_project_exits_before_generating(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_repl.active_project = None
        with patch("application.reporting.draft_runner.generate_draft") as mock_gen:
            cmd.execute("report", ["draft"])

        mock_gen.assert_not_called()
        mock_repl.console.print.assert_called()

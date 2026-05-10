"""Unit tests for ReportCommand (application.repl.commands.report)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.report import ReportCommand
from application.reporting.drafts import SECTION_REGISTRY
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

        mock_repl.console.print.assert_called()

    def test_no_active_project_prints_warning_and_returns(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_repl.active_project = None
        cmd.execute("report", [])

        mock_repl.console.print.assert_called()

    def test_format_markdown_invokes_generator(
        self,
        cmd: ReportCommand,
        mock_repl: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        mock_kb = MagicMock()
        mock_findings_service = MagicMock()
        mock_findings_service.finding_repo = MagicMock()
        with (
            patch.object(ReportCommand, "_get_knowledge_base", return_value=mock_kb),
            patch.object(ReportCommand, "_resolve_project_id", return_value=1),
            patch(
                "application.repl.commands.report.create_findings_service"
            ) as mock_create_svc,
            patch("application.reporting.generator.ReportGenerator") as mock_gen_cls,
        ):
            mock_create_svc.return_value = mock_findings_service
            cmd.execute("report", ["--format=markdown"])

        mock_gen_cls.return_value.generate.assert_called_once()

    def test_default_format_is_pdf(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        """report with no --format argument defaults to PDF assembly."""
        mock_repl.base_path = str(tmp_path)
        # Seed all draft sections so _check_drafts_present passes
        draft_dir = tmp_path / "projects" / "test-project" / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        for section in SECTION_REGISTRY:
            (draft_dir / f"{section}.md").write_text("draft", encoding="utf-8")

        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.return_value = MagicMock()
            mock_cls.return_value.render_pdf.return_value = b"%PDF"
            cmd.execute("report", [])

        mock_cls.assert_called_once()

    # _parse_value_flag: equals form

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
        mock_repl.console.print.assert_called()

    def test_format_pdf_delegates_to_assemble(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        # Seed all draft sections so _check_drafts_present passes
        draft_dir = tmp_path / "projects" / "test-project" / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        for section in SECTION_REGISTRY:
            (draft_dir / f"{section}.md").write_text("draft", encoding="utf-8")

        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.return_value = MagicMock()
            mock_cls.return_value.render_pdf.return_value = b"%PDF"
            cmd.execute("report", ["--format=pdf"])
        mock_cls.assert_called_once()
        mock_cls.return_value.build_context.assert_called_once()
        mock_cls.return_value.render_pdf.assert_called_once()

    # report assemble: deprecated

    def test_assemble_subcommand_shows_deprecation(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        cmd.execute("report", ["assemble"])
        mock_repl.console.print.assert_called()

    def test_assemble_subcommand_does_not_assemble(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            cmd.execute("report", ["assemble"])
        mock_cls.assert_not_called()

    # SectionMissingError is shown for PDF assembly

    def test_pdf_default_shows_section_missing_error(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        # Seed all draft sections so _check_drafts_present passes
        draft_dir = tmp_path / "projects" / "test-project" / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        for section in SECTION_REGISTRY:
            (draft_dir / f"{section}.md").write_text("draft", encoding="utf-8")

        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.side_effect = SectionMissingError(
                "executive-summary"
            )
            cmd.execute("report", [])
        mock_repl.console.print.assert_called()

    def test_shell_shows_section_missing_error(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            mock_cls.return_value.build_context.side_effect = SectionMissingError(
                "risk-level"
            )
            cmd.execute("report", ["shell"])
        mock_repl.console.print.assert_called()

    # _check_drafts_present

    def test_check_drafts_present_returns_false_when_sections_missing(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        # No draft files created; all sections missing
        result = cmd._check_drafts_present()
        assert result is False

    def test_check_drafts_present_returns_true_when_all_drafts_exist(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        draft_dir = tmp_path / "projects" / "test-project" / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        for section in SECTION_REGISTRY:
            (draft_dir / f"{section}.md").write_text("draft", encoding="utf-8")

        result = cmd._check_drafts_present()
        assert result is True

    def test_check_drafts_present_accepts_reviewed_files(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        reviewed_dir = tmp_path / "projects" / "test-project" / "reports" / "reviewed"
        reviewed_dir.mkdir(parents=True)
        for section in SECTION_REGISTRY:
            (reviewed_dir / f"{section}.md").write_text("reviewed", encoding="utf-8")

        result = cmd._check_drafts_present()
        assert result is True

    def test_pdf_shows_missing_draft_guidance_before_assembling(
        self, cmd: ReportCommand, mock_repl: MagicMock, tmp_path: Path
    ) -> None:
        mock_repl.base_path = str(tmp_path)
        # No draft files; _check_drafts_present should block assembly
        with patch("application.reporting.assembler.ReportAssembler") as mock_cls:
            cmd.execute("report", [])
        mock_cls.assert_not_called()

    # report draft: no-section generates all sections

    def test_draft_no_section_calls_generate_for_every_section(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_reports_service = MagicMock()
        mock_reports_service.draft_repo = MagicMock()
        with (
            patch.object(ReportCommand, "_resolve_project_id", return_value=1),
            patch(
                "application.repl.commands.report.create_reports_service"
            ) as mock_create_svc,
            patch("application.reporting.draft_orchestrator.run_draft") as mock_run,
        ):
            mock_create_svc.return_value = mock_reports_service
            cmd.execute("report", ["draft"])
        assert mock_run.call_count == len(SECTION_REGISTRY)

    def test_draft_with_section_calls_generate_once(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_reports_service = MagicMock()
        mock_reports_service.draft_repo = MagicMock()
        with (
            patch.object(ReportCommand, "_resolve_project_id", return_value=1),
            patch(
                "application.repl.commands.report.create_reports_service"
            ) as mock_create_svc,
            patch("application.reporting.draft_orchestrator.run_draft") as mock_run,
        ):
            mock_create_svc.return_value = mock_reports_service
            cmd.execute("report", ["draft", "risk-level"])
        assert mock_run.call_count == 1

    def test_draft_no_active_project_exits_before_generating(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_repl.active_project = None
        with patch("application.reporting.draft_orchestrator.run_draft") as mock_run:
            cmd.execute("report", ["draft"])
        mock_run.assert_not_called()
        mock_repl.console.print.assert_called()

    def test_draft_skip_triage_passes_flag_to_generate_draft(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_reports_service = MagicMock()
        mock_reports_service.draft_repo = MagicMock()
        with (
            patch.object(ReportCommand, "_resolve_project_id", return_value=1),
            patch(
                "application.repl.commands.report.create_reports_service"
            ) as mock_create_svc,
            patch("application.reporting.draft_orchestrator.run_draft") as mock_run,
        ):
            mock_create_svc.return_value = mock_reports_service
            cmd.execute("report", ["draft", "--skip-triage"])
        assert mock_run.call_count == len(SECTION_REGISTRY)

    def test_draft_force_and_skip_triage_together(
        self, cmd: ReportCommand, mock_repl: MagicMock
    ) -> None:
        mock_reports_service = MagicMock()
        mock_reports_service.draft_repo = MagicMock()
        with (
            patch.object(ReportCommand, "_resolve_project_id", return_value=1),
            patch(
                "application.repl.commands.report.create_reports_service"
            ) as mock_create_svc,
            patch("application.reporting.draft_orchestrator.run_draft") as mock_run,
        ):
            mock_create_svc.return_value = mock_reports_service
            cmd.execute("report", ["draft", "risk-level", "--force", "--skip-triage"])
        assert mock_run.call_count == 1

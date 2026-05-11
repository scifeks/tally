"""Unit tests for CLI argument parser."""

from __future__ import annotations

import pytest

from application.cli.parser import build_parser


class TestCommandFlag:
    def test_scan_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan"])
        assert args.command == "scan"

    def test_run_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=run", "--tool=semgrep"])
        assert args.command == "run"
        assert args.tool == "semgrep"

    def test_report_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report"])
        assert args.command == "report"

    def test_triage_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=triage"])
        assert args.command == "triage"

    def test_purge_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=purge"])
        assert args.command == "purge"

    def test_stats_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=stats"])
        assert args.command == "stats"

    def test_ui_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=ui"])
        assert args.command == "ui"

    def test_missing_command_raises_system_exit(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_invalid_command_raises_system_exit(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--command=invalid"])


class TestScanDefaults:
    def test_skip_enrichment_defaults_to_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan"])
        assert args.skip_enrichment is False

    def test_tool_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan"])
        assert args.tool is None

    def test_skip_tools_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan"])
        assert args.skip_tools is None

    def test_repo_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan"])
        assert args.repo is None

    def test_domain_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan"])
        assert args.domain is None


class TestToolMutualExclusion:
    def test_tool_and_skip_tools_are_mutually_exclusive(
        self,
    ) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--command=scan",
                    "--tool=semgrep",
                    "--skip-tools=gitleaks",
                ]
            )

    def test_tool_alone_is_allowed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan", "--tool=semgrep"])
        assert args.tool == "semgrep"

    def test_skip_tools_alone_is_allowed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan", "--skip-tools=gitleaks"])
        assert args.skip_tools == "gitleaks"


class TestCommaSeparatedValues:
    def test_comma_separated_tools(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--command=scan", "--tool=semgrep,gitleaks,truffleHog"]
        )
        assert args.tool == "semgrep,gitleaks,truffleHog"

    def test_comma_separated_repos(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan", "--repo=repo1,repo2,repo3"])
        assert args.repo == "repo1,repo2,repo3"

    def test_comma_separated_domains(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=scan",
                "--domain=api.example.com,www.example.com",
            ]
        )
        assert args.domain == "api.example.com,www.example.com"

    def test_comma_separated_skip_tools(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=scan", "--skip-tools=semgrep,gitleaks"])
        assert args.skip_tools == "semgrep,gitleaks"


class TestRunCommand:
    def test_run_with_tool(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=run", "--tool=semgrep"])
        assert args.command == "run"
        assert args.tool == "semgrep"

    def test_run_with_timeout(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=run", "--tool=semgrep", "--timeout=300"])
        assert args.timeout == 300

    def test_run_with_remainder_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=run",
                "--tool=semgrep",
                "--",
                "--verbose",
            ]
        )
        assert args.tool == "semgrep"
        assert "--verbose" in args.args

    def test_run_with_timeout_and_remainder(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=run",
                "--tool=semgrep",
                "--timeout=300",
                "--",
                "--verbose",
                "arg2",
            ]
        )
        assert args.timeout == 300
        assert "--verbose" in args.args
        assert "arg2" in args.args

    def test_timeout_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=run", "--tool=semgrep"])
        assert args.timeout is None

    def test_args_defaults_to_empty_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=run", "--tool=semgrep"])
        assert args.args == []


class TestReportCommand:
    def test_report_type_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report"])
        assert args.type is None

    def test_report_format_defaults_to_pdf(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report"])
        assert args.format == "pdf"

    def test_report_format_can_be_overridden(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report", "--format=markdown"])
        assert args.format == "markdown"

    def test_report_testing_type_defaults_to_white_box(
        self,
    ) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report"])
        assert args.testing_type == "white_box"

    def test_report_type_draft(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report", "--type=draft"])
        assert args.type == "draft"

    def test_report_draft_with_section(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=report",
                "--type=draft",
                "--section=executive_summary",
            ]
        )
        assert args.type == "draft"
        assert args.section == "executive_summary"

    def test_report_draft_force_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report", "--type=draft", "--force"])
        assert args.force is True

    def test_report_draft_skip_triage_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report", "--type=draft", "--skip-triage"])
        assert args.skip_triage is True

    def test_report_type_shell(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report", "--type=shell"])
        assert args.type == "shell"

    def test_report_shell_with_testing_type(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=report",
                "--type=shell",
                "--testing-type=black_box",
            ]
        )
        assert args.testing_type == "black_box"

    def test_report_shell_with_engagement_date(
        self,
    ) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=report",
                "--type=shell",
                "--engagement-date=2025-05-10",
            ]
        )
        assert args.engagement_date == "2025-05-10"

    def test_report_shell_with_output(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=report",
                "--type=shell",
                "--output=/tmp/report.pdf",
            ]
        )
        assert args.output == "/tmp/report.pdf"

    def test_report_type_final(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=report", "--type=final"])
        assert args.type == "final"


class TestTriageCommand:
    def test_triage_batch_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=triage", "--batch"])
        assert args.batch is True

    def test_triage_dry_run_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=triage", "--dry-run"])
        assert args.dry_run is True

    def test_triage_rebuild_container_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=triage", "--rebuild-container"])
        assert args.rebuild_container is True

    def test_triage_all_flags_together(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--command=triage",
                "--batch",
                "--dry-run",
                "--rebuild-container",
            ]
        )
        assert args.batch is True
        assert args.dry_run is True
        assert args.rebuild_container is True


class TestPurgeCommand:
    def test_purge_with_tool(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=purge", "--tool=semgrep"])
        assert args.tool == "semgrep"

    def test_purge_with_multiple_tools(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=purge", "--tool=semgrep,gitleaks"])
        assert args.tool == "semgrep,gitleaks"

    def test_purge_keep_reports_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=purge", "--keep-reports"])
        assert args.keep_reports is True


class TestGlobalFlags:
    def test_base_path_defaults_to_current_directory(
        self,
    ) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=stats"])
        assert args.base_path == "."

    def test_base_path_can_be_overridden(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--base-path=/tmp", "--command=stats"])
        assert args.base_path == "/tmp"

    def test_project_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--command=stats"])
        assert args.project is None

    def test_project_can_be_set(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--project=my_project", "--command=stats"])
        assert args.project == "my_project"

    def test_flags_can_appear_in_any_order(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--base-path=/tmp",
                "--project=proj",
                "--command=stats",
            ]
        )
        assert args.base_path == "/tmp"
        assert args.project == "proj"
        assert args.command == "stats"

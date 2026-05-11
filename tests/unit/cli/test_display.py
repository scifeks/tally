"""Unit tests for CLI display adapter."""

from __future__ import annotations

from application.cli.display import CliDisplay
from domain.tools.display import ToolDisplayRow


class TestPrintToolLineSuccess:
    def test_prints_successful_tool_with_findings(self, capsys) -> None:
        display = CliDisplay()
        row = ToolDisplayRow(
            tool_name="semgrep",
            success=True,
            skipped=False,
            finding_count=5,
            duration_seconds=3.14,
            skip_reason="",
            repo="",
        )

        display.print_tool_line(row)
        captured = capsys.readouterr()

        assert "✓" in captured.out
        assert "semgrep" in captured.out
        assert "5 findings" in captured.out
        assert "3.1s" in captured.out

    def test_prints_successful_tool_with_zero_findings(self, capsys) -> None:
        display = CliDisplay()
        row = ToolDisplayRow(
            tool_name="gitleaks",
            success=True,
            skipped=False,
            finding_count=0,
            duration_seconds=1.5,
            skip_reason="",
            repo="",
        )

        display.print_tool_line(row)
        captured = capsys.readouterr()

        assert "✓" in captured.out
        assert "gitleaks" in captured.out
        assert "0 findings" in captured.out
        assert "1.5s" in captured.out


class TestPrintToolLineFailed:
    def test_prints_failed_tool(self, capsys) -> None:
        display = CliDisplay()
        row = ToolDisplayRow(
            tool_name="semgrep",
            success=False,
            skipped=False,
            finding_count=0,
            duration_seconds=2.5,
            skip_reason="",
            repo="",
        )

        display.print_tool_line(row)
        captured = capsys.readouterr()

        assert "✗" in captured.out
        assert "semgrep" in captured.out
        assert "FAILED" in captured.out
        assert "2.5s" in captured.out


class TestPrintToolLineSkipped:
    def test_prints_skipped_tool_with_reason(self, capsys) -> None:
        display = CliDisplay()
        row = ToolDisplayRow(
            tool_name="npm_audit",
            success=False,
            skipped=True,
            finding_count=0,
            duration_seconds=0.0,
            skip_reason="no package.json found",
            repo="",
        )

        display.print_tool_line(row)
        captured = capsys.readouterr()

        assert "npm_audit" in captured.out
        assert "SKIPPED" in captured.out
        assert "no package.json found" in captured.out

    def test_prints_skipped_tool_without_reason(self, capsys) -> None:
        display = CliDisplay()
        row = ToolDisplayRow(
            tool_name="npm_audit",
            success=False,
            skipped=True,
            finding_count=0,
            duration_seconds=0.0,
            skip_reason="",
            repo="",
        )

        display.print_tool_line(row)
        captured = capsys.readouterr()

        assert "npm_audit" in captured.out
        assert "SKIPPED" in captured.out
        assert "(" not in captured.out


class TestPrintFinalLine:
    def test_prints_summary_with_all_counts(self, capsys) -> None:
        display = CliDisplay()

        display.print_final_line(run=5, failed=2, skipped=1, ingested=7, duration=42.5)
        captured = capsys.readouterr()

        assert "5 passed" in captured.out
        assert "2 failed" in captured.out
        assert "1 skipped" in captured.out
        assert "7 findings ingested" in captured.out
        assert "42.5s total" in captured.out

    def test_prints_summary_with_zero_counts(self, capsys) -> None:
        display = CliDisplay()

        display.print_final_line(run=0, failed=0, skipped=0, ingested=0, duration=0.0)
        captured = capsys.readouterr()

        assert "0 passed" in captured.out
        assert "0 failed" in captured.out
        assert "0 skipped" in captured.out
        assert "0 findings ingested" in captured.out
        assert "0.0s total" in captured.out


class TestPrintSummaryTableWithRepo:
    def test_includes_repo_column_when_any_row_has_repo(self, capsys) -> None:
        display = CliDisplay()
        rows = [
            ToolDisplayRow(
                tool_name="semgrep",
                success=True,
                skipped=False,
                finding_count=3,
                duration_seconds=2.0,
                skip_reason="",
                repo="main_repo",
            ),
            ToolDisplayRow(
                tool_name="gitleaks",
                success=True,
                skipped=False,
                finding_count=0,
                duration_seconds=1.0,
                skip_reason="",
                repo="",
            ),
        ]

        display.print_summary_table(rows)
        captured = capsys.readouterr()

        # Check header contains Repo
        assert "Repo" in captured.out
        assert "Tool" in captured.out
        assert "Status" in captured.out
        assert "Findings" in captured.out
        assert "Duration" in captured.out

    def test_omits_repo_column_when_no_rows_have_repo(self, capsys) -> None:
        display = CliDisplay()
        rows = [
            ToolDisplayRow(
                tool_name="semgrep",
                success=True,
                skipped=False,
                finding_count=3,
                duration_seconds=2.0,
                skip_reason="",
                repo="",
            ),
            ToolDisplayRow(
                tool_name="gitleaks",
                success=True,
                skipped=False,
                finding_count=0,
                duration_seconds=1.0,
                skip_reason="",
                repo="",
            ),
        ]

        display.print_summary_table(rows)
        captured = capsys.readouterr()

        # Header line should have Tool, Status, Findings, Duration but not Repo
        lines = captured.out.split("\n")
        header_line = lines[0] if lines else ""
        # Count pipes to verify structure (no Repo means fewer columns)
        repo_count = header_line.count("Repo")
        assert repo_count == 0

    def test_filters_out_skipped_rows(self, capsys) -> None:
        display = CliDisplay()
        rows = [
            ToolDisplayRow(
                tool_name="semgrep",
                success=True,
                skipped=False,
                finding_count=3,
                duration_seconds=2.0,
                skip_reason="",
                repo="",
            ),
            ToolDisplayRow(
                tool_name="npm_audit",
                success=False,
                skipped=True,
                finding_count=0,
                duration_seconds=0.0,
                skip_reason="no package.json",
                repo="",
            ),
        ]

        display.print_summary_table(rows)
        captured = capsys.readouterr()

        # semgrep should be in output, npm_audit should not
        assert "semgrep" in captured.out
        assert "npm_audit" not in captured.out

    def test_does_not_print_when_all_rows_skipped(self, capsys) -> None:
        display = CliDisplay()
        rows = [
            ToolDisplayRow(
                tool_name="npm_audit",
                success=False,
                skipped=True,
                finding_count=0,
                duration_seconds=0.0,
                skip_reason="no package.json",
                repo="",
            ),
        ]

        display.print_summary_table(rows)
        captured = capsys.readouterr()

        # Should print nothing since all rows are skipped
        assert captured.out == ""

    def test_prints_pass_fail_status_correctly(self, capsys) -> None:
        display = CliDisplay()
        rows = [
            ToolDisplayRow(
                tool_name="semgrep",
                success=True,
                skipped=False,
                finding_count=3,
                duration_seconds=2.0,
                skip_reason="",
                repo="",
            ),
            ToolDisplayRow(
                tool_name="gitleaks",
                success=False,
                skipped=False,
                finding_count=0,
                duration_seconds=1.0,
                skip_reason="",
                repo="",
            ),
        ]

        display.print_summary_table(rows)
        captured = capsys.readouterr()

        assert "pass" in captured.out
        assert "fail" in captured.out

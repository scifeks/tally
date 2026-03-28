"""Unit tests for OrchestratorDisplay (application.tools.display)."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from application.tools.display import OrchestratorDisplay
from domain.tools.display import ToolDisplayRow


def _make() -> tuple[OrchestratorDisplay, StringIO]:
    buf = StringIO()
    console = Console(file=buf, highlight=False)
    return OrchestratorDisplay(console), buf


class TestOrchestratorDisplay:
    def test_print_scan_header_contains_label(self) -> None:
        display, buf = _make()
        display.print_scan_header("My Scan")
        assert "My Scan" in buf.getvalue()

    def test_print_scan_header_contains_divider(self) -> None:
        display, buf = _make()
        display.print_scan_header("My Scan")
        assert "─" in buf.getvalue()

    def test_print_segment_header_uppercases_segment(self) -> None:
        display, buf = _make()
        display.print_segment_header("network")
        assert "NETWORK" in buf.getvalue()

    def test_print_repo_scan_header_contains_repo_name(self) -> None:
        display, buf = _make()
        display.print_repo_scan_header("my-repo", "Python", ["semgrep"])
        assert "my-repo" in buf.getvalue()

    def test_print_repo_scan_header_contains_languages(self) -> None:
        display, buf = _make()
        display.print_repo_scan_header("my-repo", "Python", ["semgrep"])
        assert "Python" in buf.getvalue()

    def test_print_repo_scan_header_contains_tool(self) -> None:
        display, buf = _make()
        display.print_repo_scan_header("my-repo", "Python", ["semgrep"])
        assert "semgrep" in buf.getvalue()

    def test_print_status_passes_through_message(self) -> None:
        display, buf = _make()
        display.print_status("Hello world")
        assert "Hello world" in buf.getvalue()

    def test_print_running_with_repo_contains_both(self) -> None:
        display, buf = _make()
        display.print_running("semgrep", "my-repo")
        text = buf.getvalue()
        assert "semgrep" in text
        assert "my-repo" in text

    def test_print_running_without_repo_omits_parens(self) -> None:
        display, buf = _make()
        display.print_running("gitleaks")
        text = buf.getvalue()
        assert "gitleaks" in text
        assert "()" not in text

    def test_print_tool_line_success_contains_check_mark(self) -> None:
        display, buf = _make()
        row = ToolDisplayRow(
            tool_name="semgrep",
            success=True,
            skipped=False,
            finding_count=3,
            duration_seconds=1.5,
        )
        display.print_tool_line(row)
        assert "✓" in buf.getvalue()

    def test_print_tool_line_success_contains_finding_count(self) -> None:
        display, buf = _make()
        row = ToolDisplayRow(
            tool_name="semgrep",
            success=True,
            skipped=False,
            finding_count=3,
            duration_seconds=1.5,
        )
        display.print_tool_line(row)
        assert "3" in buf.getvalue()

    def test_print_tool_line_failure_contains_cross_mark(self) -> None:
        display, buf = _make()
        row = ToolDisplayRow(
            tool_name="nmap",
            success=False,
            skipped=False,
            finding_count=0,
            duration_seconds=0.5,
        )
        display.print_tool_line(row)
        assert "✗" in buf.getvalue()

    def test_print_tool_line_skipped_contains_skipped(self) -> None:
        display, buf = _make()
        row = ToolDisplayRow(
            tool_name="zap",
            success=False,
            skipped=True,
            finding_count=0,
            duration_seconds=0.0,
        )
        display.print_tool_line(row)
        assert "SKIPPED" in buf.getvalue()

    def test_print_tool_line_skipped_with_reason_contains_reason(self) -> None:
        display, buf = _make()
        row = ToolDisplayRow(
            tool_name="zap",
            success=False,
            skipped=True,
            finding_count=0,
            duration_seconds=0.0,
            skip_reason="no targets",
        )
        display.print_tool_line(row)
        assert "no targets" in buf.getvalue()

    def test_print_summary_table_filters_skipped_rows(self) -> None:
        display, buf = _make()
        rows = [
            ToolDisplayRow(
                tool_name="semgrep",
                success=True,
                skipped=False,
                finding_count=2,
                duration_seconds=1.0,
            ),
            ToolDisplayRow(
                tool_name="zap",
                success=False,
                skipped=True,
                finding_count=0,
                duration_seconds=0.0,
            ),
        ]
        display.print_summary_table(rows)
        text = buf.getvalue()
        assert "semgrep" in text
        assert "zap" not in text

    def test_print_summary_table_all_skipped_produces_no_output(self) -> None:
        display, buf = _make()
        rows = [
            ToolDisplayRow(
                tool_name="zap",
                success=False,
                skipped=True,
                finding_count=0,
                duration_seconds=0.0,
            ),
        ]
        display.print_summary_table(rows)
        assert buf.getvalue().strip() == ""

    def test_print_final_line_contains_all_counts(self) -> None:
        display, buf = _make()
        display.print_final_line(run=3, failed=1, skipped=2, ingested=5, duration=10.5)
        text = buf.getvalue()
        assert "3" in text
        assert "1" in text
        assert "2" in text
        assert "5" in text
        assert "10.5" in text

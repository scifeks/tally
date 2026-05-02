"""Smoke test for NullDisplay no-op implementation."""

from __future__ import annotations

from domain.tools.display import DisplayProtocol, NullDisplay, ToolDisplayRow


class TestNullDisplay:
    def test_implements_display_protocol(self) -> None:
        assert isinstance(NullDisplay(), DisplayProtocol)

    def test_every_method_is_a_no_op(self) -> None:
        d = NullDisplay()
        d.print_scan_header("scan")
        d.print_segment_header("seg")
        d.print_repo_scan_header("repo", "py", ["semgrep"])
        d.print_status("hi")
        d.print_running("semgrep")
        d.print_running("semgrep", "repo")
        d.print_tool_line(
            ToolDisplayRow(
                tool_name="t",
                success=True,
                skipped=False,
                finding_count=0,
                duration_seconds=0.0,
            )
        )
        d.print_summary_table([])
        d.print_final_line(0, 0, 0, 0, 0.0)

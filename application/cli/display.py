"""Plain-text display adapter for CLI output."""

from __future__ import annotations

from domain.tools.display import ToolDisplayRow


class CliDisplay:
    """Prints scan output as plain text (no Rich markup)."""

    def print_scan_header(self, label: str) -> None:
        print(f"\n{label}")
        print("─" * 50)

    def print_segment_header(self, segment: str) -> None:
        print(f"\n{segment.upper()}")

    def print_repo_scan_header(
        self, repo_name: str, lang_str: str, tools: list[str]
    ) -> None:
        print(f"\nRepo Scan: {repo_name}")
        print(f"Languages: {lang_str}")
        print(f"Tools: {', '.join(tools)}\n")

    def print_status(self, message: str) -> None:
        print(message)

    def print_running(self, tool_name: str, repo_name: str = "") -> None:
        if repo_name:
            print(f"  [*] Running {tool_name} ({repo_name})...")
        else:
            print(f"  [*] Running {tool_name}...")

    def print_tool_line(self, row: ToolDisplayRow) -> None:
        if row.skipped:
            if row.skip_reason:
                print(f"  - {row.tool_name} | SKIPPED ({row.skip_reason})")
            else:
                print(f"  - {row.tool_name} | SKIPPED")
            return

        name = row.tool_name
        dur_str = f"{row.duration_seconds:.1f}s"
        if row.success:
            findings_str = f"{row.finding_count} findings"
            print(f"  ✓ {name:<22} | {findings_str:<14} | {dur_str}")
        else:
            print(f"  ✗ {name:<22} | {'FAILED':<14} | {dur_str}")

    def print_summary_table(self, rows: list[ToolDisplayRow]) -> None:
        rows = [r for r in rows if not r.skipped]
        if not rows:
            return
        show_repo = any(r.repo for r in rows)

        headers = ["Tool", "Status", "Findings", "Duration"]
        if show_repo:
            headers.insert(1, "Repo")

        print()
        header_line = " | ".join(h.ljust(10) for h in headers)
        print(header_line)
        print("-" * len(header_line))

        for r in rows:
            status = "pass" if r.success else "fail"
            findings = str(r.finding_count)
            dur = f"{r.duration_seconds:.1f}s"
            if show_repo:
                row_data = [r.tool_name, r.repo, status, findings, dur]
            else:
                row_data = [r.tool_name, status, findings, dur]
            row_line = " | ".join(str(v).ljust(10) for v in row_data)
            print(row_line)

    def print_final_line(
        self,
        run: int,
        failed: int,
        skipped: int,
        ingested: int,
        duration: float,
    ) -> None:
        print(
            f"\nScan complete: {run} passed, {failed} failed, {skipped} skipped | "
            f"{ingested} findings ingested | {duration:.1f}s total"
        )

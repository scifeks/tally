"""Rich display adapter for scan orchestration output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from domain.tools.display import ToolDisplayRow


class OrchestratorDisplay:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def print_scan_header(self, label: str) -> None:
        self.console.print(f"\n[bold cyan]{label}[/bold cyan]")
        self.console.print("─" * 50)

    def print_segment_header(self, segment: str) -> None:
        self.console.print(f"\n[bold yellow]{segment.upper()}[/bold yellow]")

    def print_repo_scan_header(
        self, repo_name: str, lang_str: str, tools: list[str]
    ) -> None:
        self.console.print(f"\n[bold cyan]Repo Scan:[/bold cyan] {repo_name}")
        self.console.print(f"Languages: {lang_str}")
        self.console.print(f"Tools: {', '.join(tools)}\n")

    def print_status(self, message: str) -> None:
        self.console.print(message)

    def print_running(self, tool_name: str, repo_name: str = "") -> None:
        if repo_name:
            self.console.print(f"  [dim][*] Running {tool_name} ({repo_name})...[/dim]")
        else:
            self.console.print(f"  [dim][*] Running {tool_name}...[/dim]")

    def print_tool_line(self, row: ToolDisplayRow) -> None:
        if row.skipped:
            if row.skip_reason:
                self.console.print(
                    f"  [dim]- {row.tool_name} | SKIPPED ({row.skip_reason})[/dim]"
                )
            else:
                self.console.print(f"  [dim]- {row.tool_name} | SKIPPED[/dim]")
            return

        name = row.tool_name
        dur_str = f"{row.duration_seconds:.1f}s"
        if row.success:
            findings_str = f"{row.finding_count} findings"
            self.console.print(
                f"  [green]✓[/green] [cyan]{name:<22}[/cyan]"
                f" | {findings_str:<14} | {dur_str}"
            )
        else:
            self.console.print(
                f"  [red]✗[/red] [cyan]{name:<22}[/cyan] | {'FAILED':<14} | {dur_str}"
            )

    def print_summary_table(self, rows: list[ToolDisplayRow]) -> None:
        rows = [r for r in rows if not r.skipped]
        if not rows:
            return
        show_repo = any(r.repo for r in rows)
        table = Table(title=None, show_header=True, header_style="bold")
        table.add_column("Tool", style="cyan")
        if show_repo:
            table.add_column("Repo", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Findings", style="white")
        table.add_column("Duration", style="white")
        for r in rows:
            status = "pass" if r.success else "fail"
            findings = str(r.finding_count)
            dur = f"{r.duration_seconds:.1f}s"
            if show_repo:
                table.add_row(r.tool_name, r.repo, status, findings, dur)
            else:
                table.add_row(r.tool_name, status, findings, dur)
        self.console.print()
        self.console.print(table)

    def print_final_line(
        self,
        run: int,
        failed: int,
        skipped: int,
        ingested: int,
        duration: float,
    ) -> None:
        self.console.print(
            f"\n[bold]Scan complete:[/bold] "
            f"[green]{run} passed[/green], "
            f"[red]{failed} failed[/red], "
            f"[dim]{skipped} skipped[/dim] | "
            f"{ingested} findings ingested | "
            f"{duration:.1f}s total"
        )

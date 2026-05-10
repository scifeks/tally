"""Rich display adapter for the dependency-checker output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape as markup_escape
from rich.table import Table

from application.startup.checker import DependencyChecker

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.startup.checker import CheckResult
    from domain.runtime.models import RuntimeDependencyStatus


def print_dependency_summary(console: Console, result: CheckResult) -> None:
    console.print("\n[bold]Installed System Tools[/bold]")
    console.print("=" * 22)

    table = Table(
        show_header=True, header_style="bold", padding=(0, 1), show_lines=True
    )
    table.add_column("Dependency", style="cyan", min_width=18)
    table.add_column("Type", min_width=12)
    table.add_column("Status", min_width=14)
    table.add_column("Install Hint")

    for check in result.checks:
        if check.installed:
            if check.warning:
                safe = markup_escape(check.version or "")
                status = f"[yellow]v {safe} (incompatible)[/yellow]"
            else:
                safe = markup_escape(check.version) if check.version else "installed"
                status = f"[green]v {safe}[/green]"
        else:
            status = "[yellow]! NOT FOUND[/yellow]"

        hint = check.install_hint or ""
        table.add_row(check.name, check.type, status, hint)

    console.print(table)

    if result.missing_optional:
        count = len(result.missing_optional)
        console.print(
            f"[yellow]Warning: {count} optional "
            f"tool{'s' if count != 1 else ''} not found. "
            f"Some scan features will be unavailable.[/yellow]"
        )

    if result.missing_required:
        count = len(result.missing_required)
        names = ", ".join(c.name for c in result.missing_required)
        console.print(f"[red]Error: {count} required dependency missing: {names}[/red]")


def print_installed_system_tools(
    console: Console,
    runtime_deps: Sequence[RuntimeDependencyStatus] | None = None,
) -> None:
    checker = DependencyChecker()
    tool_checks = checker.check_system_tools()

    console.print("\n[bold]Installed System Tools[/bold]")
    console.print("=" * 22)

    table = Table(
        show_header=True, header_style="bold", padding=(0, 1), show_lines=True
    )
    table.add_column("Dependency", style="cyan", min_width=18)
    table.add_column("Type", min_width=12)
    table.add_column("Status", min_width=14)
    table.add_column("Install Hint")

    for check in tool_checks:
        if check.installed:
            if check.warning:
                safe = markup_escape(check.version or "")
                status = f"[yellow]v {safe} (incompatible)[/yellow]"
            else:
                safe = markup_escape(check.version) if check.version else "installed"
                status = f"[green]v {safe}[/green]"
        else:
            status = "[yellow]! NOT FOUND[/yellow]"
        hint = check.install_hint or ""
        table.add_row(check.name, check.type, status, hint)

    if runtime_deps is not None:
        for dep in runtime_deps:
            if dep.installed:
                safe = markup_escape(dep.version) if dep.version else "installed"
                status = f"[green]v {safe}[/green]"
            else:
                status = "[yellow]! NOT FOUND[/yellow]"
            hint = dep.install_hint or ""
            table.add_row(dep.name, "runtime_dep", status, hint)

    console.print(table)

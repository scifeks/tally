"""Export command for the tally REPL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.export.service import ExportService
    from application.repl.interface import REPL

logger = logging.getLogger(__name__)


class ExportCommand:
    """Handler for the 'export' REPL command."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    def cmd_export(self, _cmd: str, args: list[str]) -> None:
        """Dispatch export subcommands."""
        if not args:
            self.repl.console.print(
                "Usage: export defectdojo [--run-id=<id>] [--test-connection]"
            )
            return

        target = args[0].lower()
        if target == "defectdojo":
            self._export_defectdojo(args[1:])
        else:
            self.repl.console.print(f"[red]Unknown export target:[/red] {target!r}")

    def _export_defectdojo(self, args: list[str]) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch "
                "<name>' first.[/yellow]"
            )
            return

        test_conn = "--test-connection" in args
        args = [a for a in args if a != "--test-connection"]

        run_id_str, args = self._parse_value_flag(args, "--run-id")
        run_id: int | None = None
        if run_id_str is not None:
            try:
                run_id = int(run_id_str)
            except ValueError:
                self.repl.console.print(f"[red]Invalid run ID:[/red] {run_id_str!r}")
                return

        try:
            service = self._build_service()
        except Exception as exc:
            self.repl.console.print(f"[red]{exc}[/red]")
            return

        if test_conn:
            ok = service.test_connection()
            if ok:
                self.repl.console.print(
                    "[green]DefectDojo connection successful.[/green]"
                )
            else:
                self.repl.console.print("[red]DefectDojo connection failed.[/red]")
            return

        with self.repl.console.status("Exporting findings to DefectDojo..."):
            result = service.export(run_id=run_id)

        if result.success:
            self.repl.console.print(
                f"[green]Export complete:[/green] "
                f"{result.findings_exported} exported"
                + (
                    f", {result.findings_failed} failed to map"
                    if result.findings_failed
                    else ""
                )
            )
        else:
            self.repl.console.print("[red]Export failed.[/red]")
            for error in result.errors:
                self.repl.console.print(f"  {error}")

    def _build_service(self) -> ExportService:
        from factories.export import create_export_service

        project_id = self._resolve_project_id()
        return create_export_service(
            self.repl.project_registry,
            project_id,
            self.repl.base_path,
        )

    def _resolve_project_id(self) -> int:
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            raise ValueError(f"project not found: {self.repl.active_project}")
        return row.id

    @staticmethod
    def _parse_value_flag(args: list[str], *flags: str) -> tuple[str | None, list[str]]:
        for i, token in enumerate(args):
            if token in flags and i + 1 < len(args):
                value = args[i + 1]
                return value, args[:i] + args[i + 2 :]
            for flag in flags:
                if token.startswith(f"{flag}="):
                    value = token[len(flag) + 1 :]
                    return value, args[:i] + args[i + 1 :]
        return None, args

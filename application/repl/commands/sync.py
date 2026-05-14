"""Sync command for the tally REPL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.export.service import ExportService
    from application.repl.interface import REPL

logger = logging.getLogger(__name__)

_SUPPORTED_INTEGRATIONS = ("defectdojo",)


class SyncCommand:
    """Handler for the 'sync' REPL command."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    def cmd_sync(self, _cmd: str, args: list[str]) -> None:
        integration, args = self._parse_value_flag(args, "--integration")
        if integration is None:
            self.repl.console.print(
                "Usage: sync --integration=<name> [--run-id=<id>] "
                "[--engagement-type=<type>] [--test-connection]"
            )
            return

        integration = integration.lower()
        if integration == "defectdojo":
            self._sync_defectdojo(args)
        else:
            self.repl.console.print(
                f"[red]Unknown integration:[/red]"
                f" {integration!r}\n"
                f"Available: "
                f"{', '.join(_SUPPORTED_INTEGRATIONS)}"
            )

    def _sync_defectdojo(self, args: list[str]) -> None:
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

        engagement_type, args = self._parse_value_flag(args, "--engagement-type")

        try:
            service = self._build_service(
                run_id=run_id,
                engagement_type_override=engagement_type,
            )
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

        with self.repl.console.status("Syncing findings to DefectDojo..."):
            result = service.export()

        if result.success:
            msg = f"[green]Sync complete:[/green] {result.findings_exported} exported"
            if result.findings_failed:
                msg += f", {result.findings_failed} failed to map"
            self.repl.console.print(msg)
        else:
            self.repl.console.print("[red]Sync failed.[/red]")
            for error in result.errors:
                self.repl.console.print(f"  {error}")

    def _build_service(
        self,
        run_id: int | None = None,
        engagement_type_override: str | None = None,
    ) -> ExportService:
        from factories.export import create_export_service

        project_id = self._resolve_project_id()
        return create_export_service(
            self.repl.project_registry,
            project_id,
            self.repl.base_path,
            run_id=run_id,
            engagement_type_override=engagement_type_override,
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
                    return (
                        value,
                        args[:i] + args[i + 1 :],
                    )
        return None, args

"""REPL commands for managing vulnerability reference data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.vulnerability_data.factory import (
    get_vulnerability_data_service,
)

if TYPE_CHECKING:
    from application.repl.interface import REPL


class VulnDataCommands:
    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    def cmd_vuln_data(self, _cmd: str, args: list[str]) -> None:
        sub = args[0] if args else "status"
        if sub == "update":
            self._update()
        elif sub == "status":
            self._status()
        else:
            self.repl.console.print("[yellow]Usage:[/yellow] vuln-data [status|update]")

    def _update(self) -> None:
        self.repl.console.print("Downloading vulnerability reference data...")
        try:
            svc = get_vulnerability_data_service(self.repl.base_path)
            cwe_count, epss_count = svc.update()
            self.repl.console.print(
                f"[green]Updated:[/green] {cwe_count:,} CWE "
                f"entries, {epss_count:,} EPSS scores"
            )
        except Exception as exc:
            self.repl.console.print(f"[red]Download failed:[/red] {exc}")

    def _status(self) -> None:
        svc = get_vulnerability_data_service(self.repl.base_path)
        if not svc.is_loaded():
            self.repl.console.print(
                "[yellow]No vulnerability data "
                "cached.[/yellow]\n"
                "Run 'vuln-data update' to download "
                "CWE and EPSS data."
            )
            return
        cwe_count, epss_count = svc.counts()
        self.repl.console.print(
            f"[green]Loaded:[/green] {cwe_count:,} CWE "
            f"entries, {epss_count:,} EPSS scores"
        )

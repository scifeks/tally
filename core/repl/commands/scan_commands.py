"""Scan execution commands for the tally REPL."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from core.tools.base import ToolResult
from core.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from core.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.repl.interface import REPL


def _ingest_result(repl: 'REPL', result: ToolResult, profile: Optional[str] = None) -> int:
    """Ingest a ToolResult into the project's RAG store. Returns document count."""
    from core.rag import FindingIngestor, RAGEngine

    try:
        rag_engine = RAGEngine(
            project_name=repl.active_project,
            base_path=repl.base_path,
        )
        ingestor = FindingIngestor(rag_engine, repl.active_project)
        return ingestor.ingest_tool_output(result, profile=profile)
    except (RuntimeError, ValueError) as exc:
        repl.console.print(f'[red]Ingestion error:[/red] {exc}')
        return 0


class ScanCommands:
    """Handlers for tool scan execution commands."""

    def __init__(self, repl: 'REPL') -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_scan(self, _cmd: str, args: List[str]) -> None:
        """scan -t <tool> [--timeout N] [profile]  — run a tool scan."""
        tool_name, remaining = self._parse_tool_flag(args)
        if tool_name is None:
            self.repl.console.print(
                '[red]Usage:[/red] scan -t <tool> [--timeout <seconds>] [profile]'
            )
            return

        timeout, remaining = self._parse_timeout_arg(remaining)

        if tool_name == 'nmap':
            self._cmd_scan_nmap(remaining, timeout)
        else:
            self.repl.console.print(f'[red]Unknown tool:[/red] {tool_name}')

    def cmd_run(self, _cmd: str, args: List[str]) -> None:
        """run <tool> [--timeout <seconds>] [args...]  — execute a tool with raw arguments."""
        if not args:
            self.repl.console.print(
                '[red]Usage:[/red] run <tool> [--timeout <seconds>] [args...]'
            )
            return

        tool_name = args[0].lower()
        remaining = args[1:]
        timeout, remaining = self._parse_timeout_arg(remaining)

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool(tool_name)
        if tool is None:
            self.repl.console.print(f'[red]Tool not found:[/red] {tool_name}')
            return

        if not tool.check_available():
            self.repl.console.print(
                f'[red]Tool not installed:[/red] {tool_name}. '
                f'Install with: apt install {tool_name}'
            )
            return

        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        result = executor.execute(
            tool,
            timeout=timeout,
            label='manual',
            args=' '.join(remaining),
            hosts=[],
        )

        self._print_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        if self._ask_ingest():
            count = _ingest_result(self.repl, result)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} findings[/green]')
            else:
                self.repl.console.print('[yellow]No findings to ingest.[/yellow]')

    # ------------------------------------------------------------------
    # Private — nmap scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_nmap(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('nmap')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] nmap')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] nmap. '
                'Install with: apt install nmap'
            )
            return

        profile = remaining[0] if remaining else None

        if profile:
            self.repl.console.print(f'Running nmap: {profile}...')
            self._run_nmap_profile(profile, timeout)
        else:
            profiles = self.repl.config.load_nmap_hosts(self.repl.active_project)
            if not profiles:
                self.repl.console.print(
                    '[yellow]No nmap profiles configured for this project.[/yellow]'
                )
                return

            profile_names = list(profiles.keys())
            self.repl.console.print(
                'No profile specified. Running all profiles...\n'
            )
            for i, name in enumerate(profile_names, 1):
                self.repl.console.print(
                    f'[{i}/{len(profile_names)}] Running nmap: {name}...'
                )
                self._run_nmap_profile(name, timeout)

            self.repl.console.print('\nAll scans complete.')

    def _run_nmap_profile(self, profile_name: str, timeout: int) -> None:
        result = self._execute_nmap_scan(profile_name, timeout=timeout)
        self._print_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=profile_name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} findings[/green]')
            else:
                self.repl.console.print('[yellow]No findings to ingest.[/yellow]')

    def _execute_nmap_scan(
        self,
        profile_name: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('nmap')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=profile_name,
            profile=profile_name,
            project_name=self.repl.active_project,
            base_path=self.repl.base_path,
        )

    # ------------------------------------------------------------------
    # Private — UI helpers
    # ------------------------------------------------------------------

    def _print_result(self, result: ToolResult) -> None:
        if result.success:
            summary = self._summarize_result(result)
            self.repl.console.print(f'[green]✓ Scan complete:[/green] {summary}')
        else:
            self.repl.console.print(f'[red]✗ Scan failed:[/red] {result.output}')

    def _ask_ingest(self) -> bool:
        try:
            answer = input('Ingest findings? [y/N]: ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ('y', 'yes')

    @staticmethod
    def _summarize_result(result: ToolResult) -> str:
        if not result.parsed_data:
            return 'scan complete'
        hosts = result.parsed_data.get('hosts', [])
        up_hosts = [h for h in hosts if h.get('state') == 'up']
        open_ports = sum(
            len([p for p in h.get('ports', []) if p.get('state') == 'open'])
            for h in up_hosts
        )
        return f'{len(up_hosts)} hosts up, {open_ports} open ports'

    @staticmethod
    def _parse_tool_flag(
        args: List[str],
    ) -> tuple[Optional[str], List[str]]:
        """Extract -t/--tool value. Returns (tool_name, remaining_args)."""
        for i, token in enumerate(args):
            if token in ('-t', '--tool') and i + 1 < len(args):
                tool = args[i + 1].lower()
                remaining = args[:i] + args[i + 2:]
                return tool, remaining
        return None, args

    @staticmethod
    def _parse_timeout_arg(
        args: List[str],
    ) -> tuple[int, List[str]]:
        """Extract --timeout <seconds> from args. Returns (timeout, remaining_args)."""
        for i, token in enumerate(args):
            if token == '--timeout' and i + 1 < len(args):
                raw = args[i + 1]
                try:
                    seconds = int(raw)
                    if seconds <= 0:
                        raise ValueError
                except ValueError:
                    raise ValueError(f'--timeout requires a positive integer, got {raw!r}')
                remaining = args[:i] + args[i + 2:]
                return seconds, remaining
        return DEFAULT_TIMEOUT, args

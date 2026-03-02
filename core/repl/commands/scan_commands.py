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
        elif tool_name == 'semgrep':
            self._cmd_scan_semgrep(remaining, timeout)
        elif tool_name in ('osv-scanner', 'osv'):
            self._cmd_scan_osv(remaining, timeout)
        elif tool_name == 'pip-audit':
            self._cmd_scan_pip_audit(remaining, timeout)
        elif tool_name == 'npm-audit':
            self._cmd_scan_npm_audit(remaining, timeout)
        elif tool_name == 'composer-audit':
            self._cmd_scan_composer_audit(remaining, timeout)
        elif tool_name == 'gitleaks':
            self._cmd_scan_gitleaks(remaining, timeout)
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

    #todo: These all need to be their own modules, this is getting ridiculous.
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
    # Private — semgrep scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_semgrep(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('semgrep')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] semgrep')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] semgrep. '
                'Install with: pip install semgrep'
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        self.repl.console.print(f'Running semgrep: {repo.name}...')
        result = self._execute_semgrep_scan(repo.name, repo.path, timeout=timeout)
        self._print_semgrep_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        # semgrep exits with code 1 when findings are present — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} findings[/green]')
            else:
                self.repl.console.print('[yellow]No findings to ingest.[/yellow]')

    def _execute_semgrep_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('semgrep')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — osv-scanner scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_osv(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('osv-scanner')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] osv-scanner')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] osv-scanner. '
                'Install with: go install github.com/google/osv-scanner/cmd/osv-scanner@latest'
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        self.repl.console.print(f'Running osv-scanner: {repo.name}...')
        result = self._execute_osv_scan(repo.name, repo.path, timeout=timeout)
        self._print_osv_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        # osv-scanner exits with code 1 when vulnerabilities are present — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} vulnerabilities[/green]')
            else:
                self.repl.console.print('[yellow]No vulnerabilities to ingest.[/yellow]')

    def _execute_osv_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('osv-scanner')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    def _print_osv_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_osv(result)
            self.repl.console.print(f'[green]✓ Scan complete:[/green] {summary}')
        else:
            self.repl.console.print(f'[red]✗ Scan failed:[/red] {result.output}')

    @staticmethod
    def _summarize_osv(result: ToolResult) -> str:
        if not result.parsed_data:
            return 'scan complete'
        summary = result.parsed_data.get('summary', {})
        total = summary.get('total_vulnerabilities', 0)
        by_sev = summary.get('by_severity', {})
        parts = [f'{by_sev[s]} {s}' for s in ('critical', 'high', 'medium', 'low') if by_sev.get(s)]
        sev_str = ', '.join(parts) if parts else 'none'
        return f'{total} vulnerabilities ({sev_str})'

    # ------------------------------------------------------------------
    # Public — repo-scan (language-aware multi-tool SCA)
    # ------------------------------------------------------------------

    def cmd_repo_scan(self, _cmd: str, args: List[str]) -> None:
        """repo-scan [--timeout N]  — run language-appropriate SCA tools on a repo."""
        timeout, _ = self._parse_timeout_arg(args)

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        selected_tools = self._select_repo_tools(repo.languages)
        lang_str = ', '.join(repo.languages) if repo.languages else 'unknown'
        self.repl.console.print(
            f'\nRepository: [cyan]{repo.name}[/cyan] ({lang_str})'
        )
        self.repl.console.print(
            f'Auto-selected tools: [cyan]{", ".join(selected_tools)}[/cyan]\n'
        )

        for tool_name in selected_tools:
            tool = tool_registry.get_tool(tool_name)
            if tool is None:
                self.repl.console.print(f'[yellow]Tool not found: {tool_name} — skipping[/yellow]')
                continue
            if not tool.check_available():
                self.repl.console.print(f'[yellow]{tool_name} not installed — skipping[/yellow]')
                continue

            try:
                answer = input(f'Run {tool_name}? [y/N]: ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if answer not in ('y', 'yes'):
                continue

            if tool_name == 'semgrep':
                result = self._execute_semgrep_scan(repo.name, repo.path, timeout=timeout)
                self._print_semgrep_result(result)
                if result.parsed_data and "error" not in result.parsed_data:
                    result.success = True
            elif tool_name == 'osv-scanner':
                result = self._execute_osv_scan(repo.name, repo.path, timeout=timeout)
                self._print_osv_result(result)
                if result.parsed_data and "error" not in result.parsed_data:
                    result.success = True
            elif tool_name == 'pip-audit':
                result = self._execute_pip_audit_scan(repo.name, repo.path, timeout=timeout)
                self._print_sca_result(result, 'pip-audit')
                if result.parsed_data and "error" not in result.parsed_data:
                    result.success = True
            elif tool_name == 'npm-audit':
                result = self._execute_npm_audit_scan(repo.name, repo.path, timeout=timeout)
                self._print_sca_result(result, 'npm-audit')
                if result.parsed_data and "error" not in result.parsed_data:
                    result.success = True
            elif tool_name == 'composer-audit':
                result = self._execute_composer_audit_scan(repo.name, repo.path, timeout=timeout)
                self._print_sca_result(result, 'composer-audit')
                if result.parsed_data and "error" not in result.parsed_data:
                    result.success = True
            elif tool_name == 'gitleaks':
                result = self._execute_gitleaks_scan(repo.name, repo.path, timeout=timeout)
                self._print_gitleaks_result(result)
                if result.parsed_data and "error" not in result.parsed_data:
                    result.success = True
            else:
                continue

            if result.output_files:
                for path in result.output_files.values():
                    self.repl.console.print(f'Output saved to: {path}')

            if self._ask_ingest():
                count = _ingest_result(self.repl, result, profile=repo.name)
                if tool_name == 'gitleaks':
                    label = 'secrets'
                elif tool_name == 'semgrep':
                    label = 'findings'
                else:
                    label = 'vulnerabilities'
                if count > 0:
                    self.repl.console.print(f'[green]✓ Ingested {count} {label}[/green]')
                else:
                    self.repl.console.print(f'[yellow]No {label} to ingest.[/yellow]')
            self.repl.console.print()

    # ------------------------------------------------------------------
    # Private — pip-audit scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_pip_audit(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('pip-audit')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] pip-audit')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] pip-audit. '
                'Install with: pip install pip-audit'
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        self.repl.console.print(f'Running pip-audit: {repo.name}...')
        result = self._execute_pip_audit_scan(repo.name, repo.path, timeout=timeout)
        self._print_sca_result(result, 'pip-audit')

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        # pip-audit exits with code 1 when vulnerabilities are present — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} vulnerabilities[/green]')
            else:
                self.repl.console.print('[yellow]No vulnerabilities to ingest.[/yellow]')

    def _execute_pip_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('pip-audit')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — npm-audit scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_npm_audit(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('npm-audit')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] npm-audit')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] npm-audit (requires npm). '
                'Install with: apt install nodejs npm'
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        self.repl.console.print(f'Running npm-audit: {repo.name}...')
        result = self._execute_npm_audit_scan(repo.name, repo.path, timeout=timeout)
        self._print_sca_result(result, 'npm-audit')

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        # npm audit exits with code 1 when vulnerabilities are present — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} vulnerabilities[/green]')
            else:
                self.repl.console.print('[yellow]No vulnerabilities to ingest.[/yellow]')

    def _execute_npm_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('npm-audit')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        # npm audit must run from inside the repository directory
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            cwd=repo_path,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — composer-audit scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_composer_audit(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('composer-audit')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] composer-audit')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] composer-audit (requires composer). '
                'Install with: apt install composer'
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        self.repl.console.print(f'Running composer-audit: {repo.name}...')
        result = self._execute_composer_audit_scan(repo.name, repo.path, timeout=timeout)
        self._print_sca_result(result, 'composer-audit')

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        # composer audit exits with code 1 when vulnerabilities are present — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} vulnerabilities[/green]')
            else:
                self.repl.console.print('[yellow]No vulnerabilities to ingest.[/yellow]')

    def _execute_composer_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('composer-audit')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        # composer audit must run from inside the repository directory
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            cwd=repo_path,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — gitleaks scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_gitleaks(self, remaining: List[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool('gitleaks')
        if tool is None:
            self.repl.console.print('[red]Tool not found:[/red] gitleaks')
            return

        if not tool.check_available():
            self.repl.console.print(
                '[red]Tool not installed:[/red] gitleaks. '
                'Install with: apt install gitleaks'
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. Use 'add-repo' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print('\nSelect repository:')
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f'  {i}. {r.name} ({r.path})')
            try:
                raw = input('\nChoice: ').strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print('[red]Invalid choice.[/red]')
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print('[red]Invalid choice.[/red]')
                return

        self.repl.console.print(f'Running gitleaks: {repo.name}...')
        result = self._execute_gitleaks_scan(repo.name, repo.path, timeout=timeout)
        self._print_gitleaks_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f'Output saved to: {path}')

        # gitleaks exits with code 1 when secrets are found — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f'[green]✓ Ingested {count} secrets[/green]')
            else:
                self.repl.console.print('[yellow]No secrets to ingest.[/yellow]')

    def _execute_gitleaks_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool('gitleaks')
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    def _print_gitleaks_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            total = (result.parsed_data or {}).get("summary", {}).get("total_secrets", 0)
            if total > 0:
                self.repl.console.print('[yellow]⚠  WARNING: Secrets detected![/yellow]')
            summary = self._summarize_gitleaks(result)
            self.repl.console.print(f'[green]✓ Scan complete:[/green] {summary}')
        else:
            self.repl.console.print(f'[red]✗ Scan failed:[/red] {result.output}')

    @staticmethod
    def _summarize_gitleaks(result: ToolResult) -> str:
        if not result.parsed_data:
            return 'scan complete'
        summary = result.parsed_data.get('summary', {})
        total = summary.get('total_secrets', 0)
        if total == 0:
            return '0 secrets found (clean)'
        files_count = summary.get('files_with_secrets', 0)
        by_rule = summary.get('by_rule', {})
        rule_str = ', '.join(f'{count} {rule}' for rule, count in by_rule.items())
        return f'{total} secrets in {files_count} file(s) ({rule_str})'

    # ------------------------------------------------------------------
    # Private — shared SCA result helpers
    # ------------------------------------------------------------------

    def _print_sca_result(self, result: ToolResult, tool_name: str) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_sca(result)
            self.repl.console.print(f'[green]✓ Scan complete:[/green] {summary}')
        else:
            self.repl.console.print(f'[red]✗ Scan failed:[/red] {result.output}')

    @staticmethod
    def _summarize_sca(result: ToolResult) -> str:
        if not result.parsed_data:
            return 'scan complete'
        summary = result.parsed_data.get('summary', {})
        total = summary.get('total_vulnerabilities', 0)
        by_sev = summary.get('by_severity', {})
        parts = [
            f'{by_sev[s]} {s}'
            for s in ('critical', 'high', 'medium', 'low')
            if by_sev.get(s)
        ]
        sev_str = ', '.join(parts) if parts else 'none'
        return f'{total} vulnerabilities ({sev_str})'

    @staticmethod
    def _select_repo_tools(languages: List[str]) -> List[str]:
        """Return tool names for a full repository scan.

        osv-scanner is always included as a baseline multi-ecosystem scanner.
        gitleaks is always included for secrets detection.
        Language-specific tools are added based on detected languages.
        """
        tools = ["osv-scanner"]
        lowered = {lang.lower() for lang in languages}
        if "python" in lowered:
            tools.append("pip-audit")
        if lowered & {"javascript", "typescript", "javascript/typescript", "node"}:
            tools.append("npm-audit")
        if "php" in lowered:
            tools.append("composer-audit")
        tools.append("gitleaks")
        return tools

    def _print_semgrep_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_semgrep(result)
            self.repl.console.print(f'[green]✓ Scan complete:[/green] {summary}')
        else:
            self.repl.console.print(f'[red]✗ Scan failed:[/red] {result.output}')

    @staticmethod
    def _summarize_semgrep(result: ToolResult) -> str:
        if not result.parsed_data:
            return 'scan complete'
        summary = result.parsed_data.get('summary', {})
        total = summary.get('total_findings', 0)
        by_sev = summary.get('by_severity', {})
        parts = [f'{by_sev[s]} {s}' for s in ('high', 'medium', 'low') if by_sev.get(s)]
        sev_str = ', '.join(parts) if parts else 'none'
        return f'{total} findings ({sev_str})'

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

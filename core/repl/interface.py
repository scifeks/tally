"""Interactive REPL shell for tally web app pentesting."""
import shlex
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from core.config import ConfigManager
from core.project import ProjectManager

_VERSION = '1.0'

# Custom box: vertical edge/divider lines with a header separator only.
# Each line = 4 chars: left-edge, fill, column-divider, right-edge.
_HELP_BOX = box.Box(
    "┌─┬┐\n"   # top border
    "│ ││\n"   # head row chars
    "├─┼┤\n"   # head/data separator
    "│ ││\n"   # data row chars
    "│ ││\n"   # row separator (show_lines=True only)
    "├─┼┤\n"   # foot separator
    "│ ││\n"   # foot row chars
    "└─┴┘\n"   # bottom border
)

# ---------------------------------------------------------------------------
# Help table definition: (section, command, description)
# None in the command slot = section header row
# ---------------------------------------------------------------------------
_HELP_ROWS = [
    ('Project Management', None, None),
    (None, 'project new',         'Create a new project (interactive)'),
    (None, 'project list',        'List all projects'),
    (None, 'project switch <n>',  'Switch active project'),
    (None, 'project info',        'Show active project details'),
    (None, 'repo add',            'Add a repository to the active project'),
    ('Scanning', None, None),
    (None, 'nmap scan',           'Run nmap against configured hosts'),
    (None, 'semgrep scan',        'Run semgrep static analysis'),
    (None, 'osv scan',            'Run OSV-Scanner for vulnerabilities'),
    (None, 'gitleaks scan',       'Run gitleaks secret detection'),
    (None, 'zap scan',            'Run OWASP ZAP web scan'),
    ('RAG / Analysis', None, None),
    (None, 'rag index',           'Index repositories into vector store'),
    (None, 'rag query <text>',    'Query the RAG engine'),
    ('Reporting', None, None),
    (None, 'report',              'Generate findings report'),
    ('Utility', None, None),
    (None, 'help',                'Show this help table'),
    (None, 'clear',               'Clear the screen'),
    (None, 'exit / quit',         'Exit tally'),
]

_COMPLETIONS = [
    'help', 'exit', 'quit', 'clear',
    'project new', 'project list', 'project switch', 'project info',
    'repo add',
    'nmap scan', 'semgrep scan', 'osv scan', 'gitleaks scan', 'zap scan',
    'rag index', 'rag query',
    'report',
]
# First tokens only for WordCompleter
_TOP_TOKENS = sorted({c.split()[0] for c in _COMPLETIONS})


class REPL:
    """Interactive REPL shell with Rich UI and prompt_toolkit input."""

    def __init__(self, base_path: str = '.'):
        self.base_path = base_path
        self.console = Console()
        self.config = ConfigManager(base_path)
        self.projects = ProjectManager(base_path)
        self.active_project: Optional[str] = self.projects.get_active_project()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the REPL loop."""
        self._print_banner()

        history_path = Path.home() / '.tally-repl-history'
        session: PromptSession = PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(_TOP_TOKENS, ignore_case=True),
        )

        while True:
            try:
                raw = session.prompt(self._get_prompt())
            except KeyboardInterrupt:
                # Ctrl+C — stay in loop
                continue
            except EOFError:
                # Ctrl+D — exit
                break

            raw = raw.strip()
            if not raw:
                continue

            try:
                tokens = shlex.split(raw)
            except ValueError as exc:
                self.console.print(f'[red]Parse error:[/red] {exc}')
                continue

            cmd, args = tokens[0].lower(), tokens[1:]
            try:
                self._dispatch(cmd, args)
            except EOFError:
                break

        self.console.print('Goodbye!')

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, cmd: str, args: list) -> None:
        handlers = {
            'help':     self._cmd_help,
            'clear':    self._cmd_clear,
            'exit':     self._cmd_exit,
            'quit':     self._cmd_exit,
            'project':  self._cmd_stub,
            'repo':     self._cmd_stub,
            'nmap':     self._cmd_stub,
            'semgrep':  self._cmd_stub,
            'osv':      self._cmd_stub,
            'gitleaks': self._cmd_stub,
            'zap':      self._cmd_stub,
            'rag':      self._cmd_stub,
            'report':   self._cmd_stub,
        }
        handler = handlers.get(cmd)
        if handler is None:
            self.console.print(
                f"[red]Unknown command:[/red] {cmd}\n"
                "Type [bold]help[/bold] for available commands"
            )
            return
        try:
            handler(cmd, args)
        except EOFError:
            raise
        except Exception as exc:
            self.console.print(f'[red]Error:[/red] {exc}')

    # ------------------------------------------------------------------
    # Implemented commands
    # ------------------------------------------------------------------

    def _cmd_help(self, _cmd: str, _args: list) -> None:
        table = Table(
            show_header=True,
            header_style='bold',
            box=_HELP_BOX,
            padding=(0, 1),
        )
        table.add_column('Command', style='cyan', no_wrap=True, min_width=26)
        table.add_column('Description', style='white')

        for section, command, description in _HELP_ROWS:
            if section is not None and command is None:
                # Section header
                table.add_row(f'[bold yellow]{section}[/bold yellow]', '')
            else:
                table.add_row(command, description)

        self.console.print(table)

    def _cmd_clear(self, _cmd: str, _args: list) -> None:
        self.console.clear()

    def _cmd_exit(self, _cmd: str, _args: list) -> None:
        raise EOFError  # re-use EOF path to trigger "Goodbye!"

    def _cmd_stub(self, cmd: str, args: list) -> None:
        sub = f' {args[0]}' if args else ''
        self.console.print(f'[dim]{cmd}{sub}[/dim] — coming soon')

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        if self.active_project:
            project_line = f'Active Project: [green]{self.active_project}[/green]'
        else:
            project_line = 'Active Project: [dim]No active project[/dim]'

        content = (
            f'[cyan]Tally Web App Pentesting REPL v{_VERSION}[/cyan]\n'
            'LlamaIndex + Chroma + Ollama\n'
            f'{project_line}'
        )
        self.console.print(
            Panel(content, title='[cyan]Welcome[/cyan]', expand=False)
        )

    def _get_prompt(self) -> FormattedText:
        if self.active_project:
            return FormattedText([
                ('ansigreen', f'[{self.active_project}]'),
                ('', '> '),
            ])
        return FormattedText([
            ('ansigray', '[no-project]'),
            ('', '> '),
        ])

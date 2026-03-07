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
from core.repl.commands import KnowledgeCommands, ProjectCommands, PurgeCommand, ReportCommand, ScanCommands
from core.tools.registry import print_discovery_summary, tool_registry

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
# None in the command slot = section header row.
#
# Scan tool rows are built dynamically in _cmd_help() from the live registry
# so that only configured tools appear, with their location shown.
# ---------------------------------------------------------------------------
_HELP_ROWS_TOP = [
    ('Project Management', None, None),
    (None, 'new-project',         'Create a new project (interactive)'),
    (None, 'projects',            'List all projects'),
    (None, 'switch <name>',       'Switch active project'),
    (None, 'project-info',        'Show active project details'),
    (None, 'add-repo',            'Add a repository to the active project'),
    (None, 'repos',               'List configured repositories'),
    (None, 'edit-repo <name>',    'Edit a repository\'s config'),
    (None, 'delete-repo <name>',  'Delete a repository\'s config'),
    ('Scanning', None, None),
    (None, '',                    '[dim]All commands accept --timeout <seconds>[/dim]'),
]

_HELP_ROWS_BOTTOM = [
    (None, 'repo-scan [--timeout N]',    'Run language-appropriate SCA tools on a repo'),
    (None, 'run <tool> [args...]',       'Execute a tool with raw arguments'),
    ('Knowledge Base', None, None),
    (None, 'search <query>',      'Semantic search over ingested findings'),
    (None, 'chat <message>',      'RAG-augmented chat with the LLM'),
    (None, 'stats',               'Show knowledge base statistics'),
    (None, 'purge [--tool <t>] [--profile <p>]', 'Delete findings from the knowledge base'),
    ('Reporting', None, None),
    (None, 'report',              'Generate findings report'),
    ('Utility', None, None),
    (None, 'help',                'Show this help table'),
    (None, 'clear',               'Clear the screen'),
    (None, 'exit / quit',         'Exit tally'),
]

# Canonical display order for scan tools (mirrors SCAN_SEGMENTS ordering)
_SCAN_TOOL_ORDER = [
    'nmap',
    'semgrep',
    'osv-scanner', 'pip-audit', 'npm-audit', 'composer-audit',
    'gitleaks',
    'zap',
]

_COMPLETIONS = [
    'help', 'exit', 'quit', 'clear',
    'new-project', 'projects', 'switch', 'project-info', 'add-repo',
    'repos', 'edit-repo', 'delete-repo',
    'scan', 'repo-scan', 'run',
    'search', 'chat', 'stats', 'purge',
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
        self.active_project: Optional[str] = None
        self.project_commands = ProjectCommands(self)
        self.scan_commands = ScanCommands(self)
        self.knowledge_commands = KnowledgeCommands(self)
        self.purge_commands = PurgeCommand(self)
        self.report_commands = ReportCommand(self)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the REPL loop."""
        self._print_banner()
        print_discovery_summary(self.console)

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
        pc = self.project_commands
        sc = self.scan_commands
        kc = self.knowledge_commands
        handlers = {
            'help':         self._cmd_help,
            'clear':        self._cmd_clear,
            'exit':         self._cmd_exit,
            'quit':         self._cmd_exit,
            'projects':     pc.cmd_projects,
            'switch':       pc.cmd_switch,
            'new-project':  pc.cmd_new_project,
            'add-repo':     pc.cmd_add_repo,
            'repos':        pc.cmd_repos,
            'edit-repo':    pc.cmd_edit_repo,
            'delete-repo':  pc.cmd_delete_repo,
            'project-info': pc.cmd_project_info,
            'scan':         sc.cmd_scan,
            'repo-scan':    sc.cmd_repo_scan,
            'run':          sc.cmd_run,
            'search':       kc.cmd_search,
            'chat':         kc.cmd_chat,
            'stats':        kc.cmd_stats,
            'purge':        self.purge_commands.cmd_purge,
            'report':       self.report_commands.execute,
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

        # Build the full row list: static top + dynamic tool rows + static bottom
        registered = set(tool_registry.list_tool_names())
        ordered_tools = [t for t in _SCAN_TOOL_ORDER if t in registered]
        # Any registered tools not in the canonical order go at the end
        ordered_tools += sorted(t for t in registered if t not in _SCAN_TOOL_ORDER)

        tool_rows = []
        for tool_name in ordered_tools:
            tool = tool_registry.get_tool(tool_name)
            config = tool_registry.get_tool_config(tool_name)
            location = config.location if config else 'local'

            if tool_name == 'nmap':
                cmd_str = 'scan -t nmap [profile]'
            else:
                cmd_str = f'scan -t {tool_name}'

            if location == 'docker':
                container = config.container.name if config else ''
                desc = f'{tool.description} [dim](docker: {container})[/dim]'
            else:
                desc = tool.description

            tool_rows.append((None, cmd_str, desc))

        all_rows = list(_HELP_ROWS_TOP) + tool_rows + list(_HELP_ROWS_BOTTOM)

        for section, command, description in all_rows:
            if section is not None and command is None:
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

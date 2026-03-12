"""Interactive REPL shell for tally web app security auditing."""

import shlex
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.config import ConfigManager
from core.project import ProjectManager
from core.repl.commands import (
    KnowledgeCommands,
    ProjectCommands,
    PurgeCommand,
    ReportCommand,
    ScanCommands,
    ToolCommands,
)
from core.startup.checker import print_installed_system_tools
from core.tools.constants import TOOL_DOMAIN_MAP
from core.tools.registry import print_discovery_summary

_VERSION = "1.0"

# Custom box: vertical edge/divider lines with a header separator only.
# Each line = 4 chars: left-edge, fill, column-divider, right-edge.
_HELP_BOX = box.Box(
    "┌─┬┐\n"  # top border
    "│ ││\n"  # head row chars
    "├─┼┤\n"  # head/data separator
    "│ ││\n"  # data row chars
    "├─┼┤\n"  # row separator  ← end_section=True
    "├─┼┤\n"  # foot separator
    "│ ││\n"  # foot row chars
    "└─┴┘\n"  # bottom border
)

# ---------------------------------------------------------------------------
# Help registry: (group, command, argument, description)
# command=None  → section header row; description holds the section title.
# command=_NOTE → dim informational row (no Command/Arguments cells).
# group is used by _cmd_help_scoped() to render filtered tables.
# ---------------------------------------------------------------------------
_NOTE = "_NOTE_"

_HELP_REGISTRY = [
    # Project Management
    ("project", None, None, "Project Management"),
    ("project", "project add", None, "Create a new project (interactive)"),
    (
        "project",
        "project switch",
        "<name>",
        "Switch the active project  [dim]required[/dim]",
    ),
    ("project", "project list", None, "List all projects"),
    ("project", "project info", None, "Show active project details"),
    (
        "project",
        "project delete",
        "<name>",
        "Delete a project and all its data  [dim]required[/dim]",
    ),
    # Repo Management
    ("repo", None, None, "Repo Management"),
    ("repo", "repo add", None, "Add a repository to the active project"),
    (
        "repo",
        "repo delete",
        "<name>",
        "Delete a repository's config  [dim]required[/dim]",
    ),
    (
        "repo",
        "repo edit",
        "<name>",
        "Edit a repository's config  [dim]required[/dim]",
    ),
    ("repo", "repo list", None, "List configured repositories"),
    # Scanning
    ("scan", None, None, "Scanning"),
    ("scan", "scan", None, "Run all configured tools across the active project"),
    ("scan", "scan", "--repo=<repo>", "Scope scan to a single configured repository"),
    (
        "scan",
        "scan",
        "--tool=<tool,...>",
        "Run only the specified tool(s). Comma-separated.",
    ),
    (
        "scan",
        "scan",
        "--type=<type,...>",
        "Run tools matching domain type(s). Comma-separated.",
    ),
    ("scan", "run", "<tool> [args...]", "Execute a tool with raw arguments"),
    # Tools
    ("tool", None, None, "Tools"),
    ("tool", "tool add", None, "Add a tool to the active configuration"),
    (
        "tool",
        "tool edit",
        "<name>",
        "Edit a configured tool interactively  [dim]required[/dim]",
    ),
    (
        "tool",
        "tool remove",
        "<name>",
        "Remove a tool from the configuration  [dim]required[/dim]",
    ),
    ("tool", "tool list", None, "List all configured tools and their status"),
    # Knowledge Base
    ("knowledge", None, None, "Knowledge Base"),
    ("knowledge", "chat", "<message>", "RAG-augmented chat with the LLM"),
    ("knowledge", "stats", None, "Show knowledge base statistics"),
    ("knowledge", "purge", None, "Delete findings from the knowledge base"),
    (
        "knowledge",
        "purge",
        "--tool <tool>",
        "Limit deletion to findings from one tool",
    ),
    # Search
    ("search", None, None, "Search"),
    (
        "search",
        _NOTE,
        None,
        "[dim]= exact  ~= partial  Filters combine with AND[/dim]",
    ),
    ("search", "search", "<query>", "Semantic search over ingested findings"),
    ("search", "search", "tool=<name>", "Filter by configured tool name"),
    (
        "search",
        "search",
        "type=<type>",
        "Filter by type: secret, vulnerability, weakness, misconfiguration, etc.",
    ),
    ("search", "search", "type=<t1>,<t2>", "AND-filter multiple finding types"),
    ("search", "search", "severity=<level>", "Filter by severity level"),
    ("search", "search", "<key>=<value>", "Exact match filter on metadata key"),
    ("search", "search", "<key>~=<value>", "Partial match filter on metadata key"),
    ("search", "search", "tool=<n> type=<t> severity=<s>", "Chain filters (AND)"),
    (
        "search",
        "search",
        "tool=<name> <query>",
        "Combine filters with semantic search",
    ),
    (
        "search",
        "search",
        "<filters> --page=<n>",
        "Show page N of results (default: 1)",
    ),
    (
        "search",
        "search",
        "<filters> --page-size=<n>",
        "Results per page (default: 20 semantic / 200 filter-only)",
    ),
    # Reporting
    ("reporting", None, None, "Reporting"),
    ("reporting", "report", None, "Generate findings report"),
    # Utility
    ("utility", None, None, "Utility"),
    ("utility", "help", None, "Show this help table"),
    ("utility", "clear", None, "Clear the screen"),
    ("utility", "exit / quit", None, "Exit tally"),
]

_COMPLETIONS = [
    "help",
    "exit",
    "quit",
    "clear",
    "project",
    "repo",
    "scan",
    "run",
    "tool",
    "search",
    "chat",
    "stats",
    "purge",
    "report",
]
# First tokens only for WordCompleter
_TOP_TOKENS = sorted({c.split()[0] for c in _COMPLETIONS})


_DOMAIN_KEYS_DISPLAY: dict[str, list[tuple[str, str]]] = {
    "code": [
        ("file~=<path>", "File path (partial match)"),
        ("rule=<id>", "Rule ID (exact match)"),
    ],
    "web": [
        ("url~=<url>", "URL (partial match)"),
        ("method=<method>", "HTTP method (GET, POST, ...)"),
        ("param~=<name>", "Parameter name (partial match)"),
        ("alert~=<name>", "Alert name (partial match)"),
    ],
    "network": [
        ("host=<ip>", "IP address (exact match)"),
        ("host~=<pattern>", "IP address (partial match)"),
        ("port=<number>", "Port number"),
        ("service~=<name>", "Service name (partial match)"),
        ("transport=<proto>", "Transport protocol (tcp, udp)"),
    ],
}

_TOOL_EXAMPLES: dict[str, list[tuple[str, str]]] = {
    "nmap": [
        ("search nmap", "All nmap findings"),
        ("search host=10.0.0.1", "Exact host match"),
        ("search port=443", "Findings on port 443"),
        ("search service~=ssh", "Services containing 'ssh'"),
        ("search transport=tcp severity=high", "High-severity TCP findings"),
        ("search nmap open ports", "Semantic search filtered to nmap"),
    ],
    "gitleaks": [
        ("search gitleaks", "All gitleaks findings"),
        ("search file~=config", "Secrets in paths containing 'config'"),
        ("search rule=generic-api-key", "Findings matching a specific rule"),
        ("search severity=high", "High-severity secrets"),
        ("search gitleaks aws", "Semantic search for AWS secrets"),
    ],
    "zap": [
        ("search zap", "All ZAP findings"),
        ("search url~=/api/", "Findings on API endpoints"),
        ("search method=POST", "POST request findings"),
        ("search param~=id", "Findings with 'id' in parameter name"),
        ("search alert~=injection", "Injection-related alerts"),
        ("search zap severity=high", "High-severity ZAP findings"),
    ],
    "semgrep": [
        ("search semgrep", "All semgrep findings"),
        ("search file~=src/auth", "Findings in auth source files"),
        ("search rule=python.lang.security.audit.exec", "Findings by rule ID"),
        ("search severity=high", "High-severity findings"),
        ("search semgrep sql injection", "Semantic search for SQL injection"),
    ],
}

_GENERIC_EXAMPLES: list[tuple[str, str]] = [
    ("search sql injection", "Semantic search for SQL injection"),
    ("search tool=gitleaks", "All gitleaks findings"),
    ("search severity=high", "High-severity findings"),
    ("search type=secret", "Findings of type 'secret'"),
    ("search tool=nmap port=443", "nmap findings on port 443"),
    ("search tool=zap url~=/api/", "ZAP findings on /api/ endpoints"),
    ("search tool=gitleaks severity=high --page-size=50", "Paginated results"),
]


def _build_search_help_table(tool_name: str | None = None) -> Table:
    """Build a search reference table, optionally narrowed to a tool's domain."""
    domain = TOOL_DOMAIN_MAP.get(tool_name) if tool_name else None
    show_code = domain in (None, "code")
    show_web = domain in (None, "web")
    show_network = domain in (None, "network")

    table = Table(
        show_header=True,
        header_style="bold",
        box=_HELP_BOX,
        padding=(0, 1),
    )
    table.add_column("Search Syntax", min_width=40, no_wrap=True, style="cyan")
    table.add_column("Description", style="white")

    # Syntax hint
    table.add_row("[bold yellow]Search Syntax[/bold yellow]", "")
    table.add_row("= exact match  ~= partial/contains  filters use AND", "")

    # Usage examples
    table.add_row("[bold yellow]Usage[/bold yellow]", "")
    table.add_row("search <query>", "Semantic search over ingested findings")
    table.add_row("search tool=<name>", "Filter by configured tool name")
    table.add_row("search type=<type>", "Filter by type: secret, vulnerability, ...")
    table.add_row("search <key>=<value>", "Exact match filter on metadata key")
    table.add_row("search <key>~=<value>", "Partial match filter on metadata key")
    table.add_row("search tool=<n> type=<t> severity=<s>", "Chain filters (AND)")
    table.add_row("search tool=<name> <query>", "Combine filters with semantic search")

    # Global filter keys
    table.add_row("[bold yellow]Global Filter Keys[/bold yellow]", "")
    table.add_row("tool=<name>", "Configured tool name")
    table.add_row("domain=<domain>", "code, web, network")
    table.add_row(
        "type=<type>", "secret, vulnerability, weakness, misconfiguration, ..."
    )
    table.add_row("severity=<level>", "critical, high, medium, low, informational")
    table.add_row("confidence=<level>", "confirmed, probable, potential")
    table.add_row("risk_type=<value>", "Risk type label (tool-specific)")
    table.add_row("profile=<value>", "Scan profile label")

    # Domain-specific keys
    if show_code:
        table.add_row("[bold yellow]Code Domain Keys[/bold yellow]", "")
        for syntax, desc in _DOMAIN_KEYS_DISPLAY["code"]:
            table.add_row(syntax, desc)

    if show_web:
        table.add_row("[bold yellow]Web Domain Keys[/bold yellow]", "")
        for syntax, desc in _DOMAIN_KEYS_DISPLAY["web"]:
            table.add_row(syntax, desc)

    if show_network:
        table.add_row("[bold yellow]Network Domain Keys[/bold yellow]", "")
        for syntax, desc in _DOMAIN_KEYS_DISPLAY["network"]:
            table.add_row(syntax, desc)

    # Pagination
    table.add_row("[bold yellow]Pagination[/bold yellow]", "")
    table.add_row(
        "--page-size=<n>", "Results per page (default: 20 semantic / 200 filter-only)"
    )
    table.add_row("--page=<n>", "Show page N of results (default: 1)")

    # Examples
    table.add_row("[bold yellow]Examples[/bold yellow]", "")
    examples = _TOOL_EXAMPLES.get(tool_name) if tool_name else None  # type: ignore[arg-type]
    if examples is None:
        examples = _GENERIC_EXAMPLES
    for syntax, desc in examples:
        table.add_row(syntax, desc)

    return table


class REPL:
    """Interactive REPL shell with Rich UI and prompt_toolkit input."""

    def __init__(self, base_path: str = "."):
        self.base_path = base_path
        self.console = Console()
        self.config = ConfigManager(base_path)
        self.projects = ProjectManager(base_path)
        self.active_project: str | None = None
        self.project_commands = ProjectCommands(self)
        self.scan_commands = ScanCommands(self)
        self.knowledge_commands = KnowledgeCommands(self)
        self.purge_commands = PurgeCommand(self)
        self.report_commands = ReportCommand(self)
        self.tool_commands = ToolCommands(self)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the REPL loop."""
        self.console.print(
            "[dim]Run 'tally --check' to see full dependency status at any time.[/dim]"
        )
        self._print_banner()
        print_installed_system_tools(self.console)
        print_discovery_summary(self.console)

        history_path = Path.home() / ".tally-repl-history"
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
                self.console.print(f"[red]Parse error:[/red] {exc}")
                continue

            cmd, args = tokens[0].lower(), tokens[1:]
            try:
                self._dispatch(cmd, args)
            except EOFError:
                break

        self.console.print("Goodbye!")

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, cmd: str, args: list) -> None:
        pc = self.project_commands
        sc = self.scan_commands
        kc = self.knowledge_commands
        tc = self.tool_commands
        handlers = {
            "help": self._cmd_help,
            "clear": self._cmd_clear,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "project": pc.cmd_project,
            "repo": pc.cmd_repo,
            "scan": sc.cmd_scan,
            "run": sc.cmd_run,
            "tool": tc.cmd_tool,
            "search": kc.cmd_search,
            "chat": kc.cmd_chat,
            "stats": kc.cmd_stats,
            "purge": self.purge_commands.cmd_purge,
            "report": self.report_commands.execute,
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
            self.console.print(f"[red]Error:[/red] {exc}")

    # ------------------------------------------------------------------
    # Implemented commands
    # ------------------------------------------------------------------

    def _cmd_help(self, _cmd: str, args: list) -> None:
        if args and args[0] == "search":
            self._cmd_help_search(args[1:])
            return
        self.console.print(self._build_help_table())

    def _cmd_help_search(self, args: list[str]) -> None:
        tool_name: str | None = args[0] if args else None
        if tool_name is not None:
            commands = self.config.load_commands_config() or {}
            if tool_name not in commands:
                self.console.print(
                    f"[red]Unknown tool {tool_name!r}.[/red] "
                    "Run 'tool list' to see configured tools."
                )
                return
        self.console.print(_build_search_help_table(tool_name))

    def _cmd_help_scoped(self, group: str) -> None:
        """Render a help table filtered to a single group (e.g. 'project', 'repo')."""
        self.console.print(self._build_help_table(group=group))

    def _build_help_table(self, group: str | None = None) -> Table:
        """Build and return a Rich Table from _HELP_REGISTRY, optionally filtered
        by group.
        """
        from collections import Counter

        table = Table(
            show_header=True,
            header_style="bold",
            box=_HELP_BOX,
            padding=(0, 1),
        )
        table.add_column("Command", style="cyan", no_wrap=True, min_width=20)
        table.add_column("Arguments", style="cyan", no_wrap=True, min_width=26)
        table.add_column("Description", style="white")

        entries = [e for e in _HELP_REGISTRY if group is None or e[0] == group]

        cmd_counts: Counter[str] = Counter(
            cmd for _, cmd, _, _ in entries if cmd is not None and cmd != _NOTE
        )
        last_row_idx: dict[str, int] = {}
        for i, (_, cmd, _, _) in enumerate(entries):
            if cmd is not None and cmd != _NOTE:
                last_row_idx[cmd] = i

        prev_cmd: str | None = None
        for i, (_, cmd, arg, desc) in enumerate(entries):
            if cmd is None:
                table.add_row(f"[bold yellow]{desc}[/bold yellow]", "", "")
                prev_cmd = None
            elif cmd == _NOTE:
                table.add_row("", "", desc)
            else:
                cmd_cell = cmd if cmd != prev_cmd else ""
                arg_cell = arg if arg is not None else ""
                is_last = last_row_idx[cmd] == i
                end_sec = is_last and cmd_counts[cmd] > 1
                table.add_row(cmd_cell, arg_cell, desc, end_section=end_sec)
                prev_cmd = cmd

        return table

    def _cmd_clear(self, _cmd: str, _args: list) -> None:
        self.console.clear()

    def _cmd_exit(self, _cmd: str, _args: list) -> None:
        raise EOFError  # re-use EOF path to trigger "Goodbye!"

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        if self.active_project:
            project_line = f"Active Project: [green]{self.active_project}[/green]"
        else:
            project_line = "Active Project: [dim]No active project[/dim]"

        content = (
            f"[cyan]Tally Web App Security Auditing REPL v{_VERSION}[/cyan]\n"
            "LlamaIndex + Chroma + Ollama\n"
            f"{project_line}"
        )
        self.console.print(Panel(content, title="[cyan]Welcome[/cyan]", expand=False))

    def _get_prompt(self) -> FormattedText:
        if self.active_project:
            return FormattedText(
                [
                    ("ansigreen", f"[{self.active_project}]"),
                    ("", "> "),
                ]
            )
        return FormattedText(
            [
                ("ansigray", "[no-project]"),
                ("", "> "),
            ]
        )

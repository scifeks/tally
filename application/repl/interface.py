"""Interactive REPL shell for tally web app security auditing."""

import logging
import os
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from application.ports.web_ui_runner import WebUiRunnerPort
from application.project import InteractiveProjectWizard
from application.project.manager import ProjectManager
from application.project.registry_service import ProjectRegistryService
from application.rag.ingestor import get_tool_domain
from application.repl.adapters.dependency_summary_display import (
    print_installed_system_tools,
)
from application.repl.adapters.tool_registry_display import print_discovery_summary
from application.repl.commands import (
    DocumentCommands,
    KnowledgeCommands,
    McpCommands,
    ProjectCommands,
    PurgeCommand,
    ReportCommand,
    ScanCommands,
    SyncCommand,
    ToolCommands,
    TriageCommands,
    UiCommands,
    VulnDataCommands,
)
from application.repl.help_renderer import HELP_BOX, HelpRenderer
from application.runtime import (
    RuntimeDependencyService,
    build_runtime_dependency_probes,
)
from application.tools.registry import ToolRegistry, discover_tools
from application.triage.readiness import compute_triage_readiness
from core.config import ConfigManager

if TYPE_CHECKING:
    from application.rag.document_store import DocumentStore
    from application.rag.knowledge_base import FindingKnowledgeBase

_log = logging.getLogger(__name__)

# When TALLY_HARNESS=1 the REPL uses plain stdin instead of prompt_toolkit.
# The sentinel is printed to stdout before each prompt so the consumer
# can reliably detect when the REPL is ready for input.
_HARNESS_SENTINEL = "__TALLY_PROMPT__"

_VERSION = "1.0"

_COMPLETIONS = [
    "help",
    "exit",
    "quit",
    "clear",
    "docs",
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
    "triage",
    "sync",
    "ui",
    "vuln-data",
    "mcp token create",
    "mcp token list",
    "mcp token revoke",
]
# First tokens only for WordCompleter
_TOP_TOKENS = sorted({c.split()[0] for c in _COMPLETIONS})


_DOMAIN_KEYS_DISPLAY: dict[str, list[tuple[str, str]]] = {
    "code": [
        ("--file~=<path>", "File path (partial match)"),
        ("--rule=<id>", "Rule ID (exact match)"),
    ],
    "web": [
        ("--url~=<url>", "URL (partial match)"),
        ("--method=<method>", "HTTP method (GET, POST, ...)"),
        ("--param~=<name>", "Parameter name (partial match)"),
        ("--alert~=<name>", "Alert name (partial match)"),
    ],
}

_TOOL_EXAMPLES: dict[str, list[tuple[str, str]]] = {
    "gitleaks": [
        ("search --tool=gitleaks", "All gitleaks findings"),
        ("search --file~=config", "Secrets in paths containing 'config'"),
        ("search --rule=generic-api-key", "Findings matching a specific rule"),
        ("search --severity=high", "High-severity secrets"),
        ("search --tool=gitleaks --severity=high", "High-severity gitleaks findings"),
    ],
    "zap": [
        ("search --tool=zap", "All ZAP findings"),
        ("search --url~=/api/", "Findings on API endpoints"),
        ("search --method=POST", "POST request findings"),
        ("search --param~=id", "Findings with 'id' in parameter name"),
        ("search --alert~=injection", "Injection-related alerts"),
        ("search --tool=zap --severity=high", "High-severity ZAP findings"),
    ],
    "semgrep": [
        ("search --tool=semgrep", "All semgrep findings"),
        ("search --file~=src/auth", "Findings in auth source files"),
        ("search --rule=python.lang.security.audit.exec", "Findings by rule ID"),
        ("search --severity=high", "High-severity findings"),
        ("search --tool=semgrep --severity=high", "High-severity semgrep findings"),
    ],
}

_GENERIC_EXAMPLES: list[tuple[str, str]] = [
    ("search --tool=gitleaks", "All gitleaks findings"),
    ("search --severity=high", "High-severity findings"),
    ("search --type=secret", "Findings of type 'secret'"),
    ("search --tool=zap --url~=/api/", "ZAP findings on /api/ endpoints"),
    ("search --file~=config", "Secrets in paths containing 'config'"),
    ("search --tool=gitleaks --severity=high --page-size=50", "Paginated results"),
]


def _build_search_help_table(tool_name: str | None = None) -> Table:
    """Build a search reference table, optionally narrowed to a tool's domain."""
    domain = get_tool_domain(tool_name) if tool_name else None
    show_code = domain in (None, "code")
    show_web = domain in (None, "web")

    table = Table(
        show_header=True,
        header_style="bold",
        box=HELP_BOX,
        padding=(0, 1),
    )
    table.add_column("Search Syntax", min_width=40, no_wrap=True, style="cyan")
    table.add_column("Description", style="white")

    # Syntax hint
    table.add_row("[bold yellow]Search Syntax[/bold yellow]", "")
    table.add_row(
        "--flag=value exact  --flag~=value partial  flags combine with AND", ""
    )
    table.add_row(
        "Bare words and key=value (without --) are rejected as old syntax.", ""
    )

    # Usage examples
    table.add_row("[bold yellow]Usage[/bold yellow]", "")
    table.add_row("search --tool=<name>", "Filter by configured tool name")
    table.add_row(
        "search --type=<type>",
        "Filter by finding type: secret, vulnerability, ...",
    )
    table.add_row("search --domain=<domain>", "Filter by domain: code, web")
    table.add_row("search --<field>=<value>", "Exact match filter on metadata key")
    table.add_row("search --<field>~=<value>", "Partial match filter on metadata key")
    table.add_row("search --tool=<n> --type=<t> --severity=<s>", "Chain filters (AND)")
    table.add_row("search --help", "Show this reference inline")

    # Global filter keys
    table.add_row("[bold yellow]Global Filter Keys[/bold yellow]", "")
    table.add_row("--tool=<name,...>", "Configured tool name(s). Comma-separated.")
    table.add_row("--domain=<domain>", "code, web")
    table.add_row(
        "--type=<type,...>",
        "secret, vulnerability, weakness, misconfiguration, ...",
    )
    table.add_row(
        "--severity=<level,...>", "critical, high, medium, low, informational"
    )
    table.add_row("--confidence=<level>", "confirmed, probable, potential")
    table.add_row("--risk_type=<value>", "Risk type label (tool-specific)")
    table.add_row("--profile=<value>", "Scan profile label")

    # Domain-specific keys
    if show_code:
        table.add_row("[bold yellow]Code Domain Keys[/bold yellow]", "")
        for syntax, desc in _DOMAIN_KEYS_DISPLAY["code"]:
            table.add_row(syntax, desc)

    if show_web:
        table.add_row("[bold yellow]Web Domain Keys[/bold yellow]", "")
        for syntax, desc in _DOMAIN_KEYS_DISPLAY["web"]:
            table.add_row(syntax, desc)

    # Pagination
    table.add_row("[bold yellow]Pagination[/bold yellow]", "")
    table.add_row(
        "--page-size=<n>", "Results per page (default: 20 semantic / 200 filter-only)"
    )
    table.add_row("--page=<n>", "Show page N of results (default: 1)")

    # Field selection
    table.add_row("[bold yellow]Field Selection[/bold yellow]", "")
    table.add_row(
        "--show-fields",
        "Show all available filter/display fields for the specified tool. "
        "Must be used with --tool=<name> only.",
    )
    table.add_row(
        "--fields=<f1,f2,...>",
        "Comma-separated list of columns to display in results. "
        "Supports both schema columns and tool-specific meta fields. "
        "Missing values render as N/A.",
    )

    # Examples
    table.add_row("[bold yellow]Examples[/bold yellow]", "")
    examples = _TOOL_EXAMPLES.get(tool_name) if tool_name is not None else None
    if examples is None:
        examples = _GENERIC_EXAMPLES
    for syntax, desc in examples:
        table.add_row(syntax, desc)

    return table


class REPL:
    """Interactive REPL shell with Rich UI and prompt_toolkit input."""

    def __init__(
        self,
        base_path: str = ".",
        runtime_service: RuntimeDependencyService | None = None,
        project_registry: ProjectRegistryService | None = None,
        web_ui_runner: WebUiRunnerPort | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.base_path = base_path
        self.console = Console()
        if project_registry is None:
            from factories.persistence import (
                build_default_registry,
            )

            project_registry = build_default_registry(base_path)
        self.project_registry = project_registry
        self.config = ConfigManager(base_path)
        self.projects = ProjectManager(base_path, registry=project_registry)
        self.wizard = InteractiveProjectWizard(self.projects)
        self.active_project: str | None = None
        self.knowledge_base_cache: dict[str, FindingKnowledgeBase | None] = {}
        self.document_store_cache: dict[str, DocumentStore | None] = {}
        if runtime_service is None:
            runtime_service = RuntimeDependencyService(
                build_runtime_dependency_probes(base_path=base_path)
            )
        self._runtime_service = runtime_service
        claude_api_key = (
            self.config.global_config.claude.api_key
            if self.config.global_config.claude
            else ""
        )
        self.triage_readiness = compute_triage_readiness(
            base_path=base_path,
            docker_available=runtime_service.is_installed("docker"),
            claude_api_key=claude_api_key,
        )
        if web_ui_runner is None:
            from infrastructure.web_ui.runner import WebUiRunner
            from web.server import create_web_app

            web_ui_runner = WebUiRunner(create_web_app)
        if tool_registry is None:
            tool_registry = ToolRegistry()
            discover_tools(tool_registry, base_path)
        self.tool_registry = tool_registry
        self.help_renderer = HelpRenderer(
            self.console,
            triage_readiness=self.triage_readiness,
        )
        self.project_commands = ProjectCommands(self, self.help_renderer)
        self.scan_commands = ScanCommands(self)
        self.knowledge_commands = KnowledgeCommands(self)
        self.purge_commands = PurgeCommand(self)
        self.report_commands = ReportCommand(self)
        self.tool_commands = ToolCommands(self, self.help_renderer)
        self.triage_commands = TriageCommands(self)
        self.sync_commands = SyncCommand(self)
        self.ui_commands = UiCommands(self, web_ui_runner=web_ui_runner)
        self.vuln_data_commands = VulnDataCommands(self)
        self.document_commands = DocumentCommands(self)
        self.mcp_commands = McpCommands(self)

    def run(self) -> None:
        """Start the REPL loop."""
        if os.getenv("TALLY_HARNESS"):
            self._run_harness()
            return
        self.console.print(
            "[dim]Run 'tally --check' to see full dependency status at any time.[/dim]"
        )
        self._print_banner()
        print_installed_system_tools(
            self.console, runtime_deps=self._runtime_service.statuses()
        )
        print_discovery_summary(self.console, self.tool_registry)

        history_path = Path.home() / ".tally-repl-history"
        session: PromptSession = PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(_TOP_TOKENS, ignore_case=True),
        )

        while True:
            try:
                raw = session.prompt(self._get_prompt())
            except KeyboardInterrupt:
                # Ctrl+C: stay in loop
                continue
            except EOFError:
                # Ctrl+D: exit
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

        self._cancel_active_scans()
        self.console.print("Goodbye!")

    def _cancel_active_scans(self) -> None:
        from application.tools.scan_run_registry import (
            get_scan_run_registry,
        )

        handles = get_scan_run_registry().list_all()
        for handle in handles:
            handle.cancel_token.set()
        if handles:
            self.console.print(
                f"[dim]Cancelling {len(handles)} active scan(s)...[/dim]"
            )

    def _run_harness(self) -> None:
        """Plain-stdin REPL loop (prints sentinel before each prompt)."""
        self._print_banner()
        print_installed_system_tools(
            self.console, runtime_deps=self._runtime_service.statuses()
        )
        print_discovery_summary(self.console, self.tool_registry)

        while True:
            sys.stdout.write(_HARNESS_SENTINEL + "\n")
            sys.stdout.flush()
            try:
                raw = sys.stdin.readline()
            except EOFError:
                break
            if not raw:
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
            "docs": self.document_commands.cmd_docs,
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
            "triage": self.triage_commands.cmd_triage,
            "sync": self.sync_commands.cmd_sync,
            "ui": self.ui_commands.cmd_ui,
            "vuln-data": self.vuln_data_commands.cmd_vuln_data,
            "mcp": self.mcp_commands.cmd_mcp,
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
            _log.exception("Command %r raised an unhandled exception", cmd)
            self.console.print(f"[red]Error:[/red] {exc}")

    def _cmd_help(self, _cmd: str, args: list) -> None:
        if args and args[0] == "search":
            self._cmd_help_search(args[1:])
            return
        self.help_renderer.render_all()

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

    def _cmd_clear(self, _cmd: str, _args: list) -> None:
        self.console.clear()

    def _cmd_exit(self, _cmd: str, _args: list) -> None:
        raise EOFError  # re-use EOF path to trigger "Goodbye!"

    def _print_banner(self) -> None:
        if self.active_project:
            project_line = f"Active Project: [green]{self.active_project}[/green]"
        else:
            project_line = "Active Project: [dim]No active project[/dim]"

        content = (
            f"[cyan]Tally Security Auditing Platform v{_VERSION}[/cyan]\n"
            "LlamaIndex + Chroma + Local Inference\n"
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

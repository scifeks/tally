"""Help table renderer for the tally REPL."""

from rich import box
from rich.console import Console
from rich.table import Table

# Custom box: vertical edge/divider lines with a header separator only.
# Each line = 4 chars: left-edge, fill, column-divider, right-edge.
HELP_BOX = box.Box(
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
# group is used by HelpRenderer.render() to render filtered tables.
# ---------------------------------------------------------------------------
_NOTE = "_NOTE_"

_HELP_REGISTRY = [
    # Project Management
    ("project", None, None, "Project Management"),
    ("project", "project add", None, "Create a new project (interactive)"),
    ("project", "project edit", "[<name>]", "Edit project settings (interactive)"),
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
        "--domain=<domain,...>",
        "Filter by domain: code, web, network. Comma-separated.",
    ),
    # Manual Run
    ("run", None, None, "Manual Run"),
    ("run", "run", "<tool> [args...]", "Execute a tool with raw arguments"),
    # Tools
    ("tool", None, None, "Tools"),
    ("tool", "tool add", None, "Add a tool to the active configuration"),
    ("tool", "tool add", "--project=<name>", "Add or override a tool for a project"),
    (
        "tool",
        "tool edit",
        "<name>",
        "Edit a configured tool interactively  [dim]required[/dim]",
    ),
    (
        "tool",
        "tool edit",
        "<name> --project=<name>",
        "Edit a project-level tool override  [dim]required[/dim]",
    ),
    (
        "tool",
        "tool remove",
        "<name>",
        "Remove a tool from the configuration  [dim]required[/dim]",
    ),
    (
        "tool",
        "tool remove",
        "<name> --project=<name>",
        "Remove a project-level tool override  [dim]required[/dim]",
    ),
    ("tool", "tool list", None, "List all configured tools and their status"),
    ("tool", "tool list", "--project=<name>", "List project-level tool overrides"),
    # Knowledge Base
    ("knowledge", None, None, "Knowledge Base"),
    ("knowledge", "chat", "<message>", "RAG-augmented chat with the LLM"),
    ("knowledge", "stats", None, "Show knowledge base statistics"),
    ("knowledge", "purge", None, "Delete findings from the knowledge base"),
    (
        "knowledge",
        "purge",
        "--tool=<tool,...>",
        "Limit deletion to the specified tool(s). Comma-separated.",
    ),
    # Report
    ("report", None, None, "Report"),
    ("report", "report", None, "Generate a findings report (markdown by default)"),
    (
        "report",
        "report",
        "--format=<fmt>",
        "Output format: markdown (default), html, json, pdf",
    ),
    (
        "report",
        "report",
        "--output=<path>",
        "Write report to a specific file path",
    ),
    (
        "report",
        "report assemble",
        None,
        "Assemble full PDF with LLM drafts and all findings",
    ),
    (
        "report",
        "report assemble",
        "--testing-type <type>",
        "white_box (default), grey_box, or black_box",
    ),
    (
        "report",
        "report assemble",
        "--output <path>",
        "Write PDF to a specific file path",
    ),
    (
        "report",
        "report draft",
        None,
        "Generate LLM drafts for all six report sections",
    ),
    (
        "report",
        "report draft",
        "<section>",
        "Generate an LLM draft for one section only",
    ),
    (
        "report",
        "report draft",
        "<section> --force",
        "Overwrite an existing draft without prompting",
    ),
    (
        "report",
        "report shell",
        None,
        "Render a shell PDF for visual layout inspection",
    ),
    (
        "report",
        "report shell",
        "--output <path>",
        "Write shell PDF to a specific file path",
    ),
    # Search
    ("search", None, None, "Search"),
    ("search", "search", None, "Search findings. Run 'search --help' for full docs."),
    (
        "search",
        "search",
        "--tool=<tool,...>",
        "Filter by configured tool name(s). Comma-separated.",
    ),
    (
        "search",
        "search",
        "--type=<type,...>",
        "Filter by finding type: secret, vulnerability, ... Comma-separated.",
    ),
    (
        "search",
        "search",
        "--domain=<domain,...>",
        "Filter by domain: code, web, network. Comma-separated.",
    ),
    (
        "search",
        "search",
        "--severity=<level,...>",
        "Filter by severity level(s). Comma-separated.",
    ),
    (
        "search",
        "search",
        "--<field>=<value>",
        "Exact metadata filter. Quote values with spaces.",
    ),
    ("search", "search", "--<field>~=<value>", "Partial (LIKE) metadata filter."),
    ("search", "search", "--page=<n>", "Show page N of results (default: 1)."),
    (
        "search",
        "search",
        "--page-size=<n>",
        "Results per page (default: 200 / 20 semantic).",
    ),
    (
        "search",
        "search",
        "--show-fields",
        "List available fields for a tool. Requires --tool=<name>.",
    ),
    (
        "search",
        "search",
        "--fields=<f1,f2,...>",
        "Comma-separated columns to display in results.",
    ),
    ("search", "search", "--help", "Show detailed search documentation inline."),
    # Triage
    ("triage", None, None, "Triage"),
    (
        "triage",
        "triage",
        None,
        "Run AI triage on untriaged findings for the active project",
    ),
    (
        "triage",
        "triage",
        "--batch",
        "Run batching phase only — no Claude sessions",
    ),
    (
        "triage",
        "triage",
        "--dry-run",
        "Batch + render prompts to DEBUG log — no MCP server, no Claude",
    ),
    # Utility
    ("utility", None, None, "Utility"),
    ("utility", "help", None, "Show this help table"),
    ("utility", "clear", None, "Clear the screen"),
    ("utility", "exit / quit", None, "Exit tally"),
]


class HelpRenderer:
    """Renders help tables filtered by group or in full."""

    def __init__(self, console: Console) -> None:
        self.console = console

    def render(self, group: str) -> None:
        """Render a help table filtered to a single group."""
        self.console.print(self._build_table(group=group))

    def render_all(self) -> None:
        """Render the full help table."""
        self.console.print(self._build_table())

    def _build_table(self, group: str | None = None) -> Table:
        """Build and return a Rich Table from _HELP_REGISTRY, optionally filtered
        by group.
        """
        table = Table(
            show_header=True,
            header_style="bold",
            box=HELP_BOX,
            padding=(0, 1),
        )
        table.add_column("Command", style="cyan", no_wrap=True, min_width=20)
        table.add_column("Arguments", style="cyan", no_wrap=True, min_width=26)
        table.add_column("Description", style="white")

        entries = [e for e in _HELP_REGISTRY if group is None or e[0] == group]

        # Collect titles of section headers that need a divider above them —
        # every header except the first one in the (filtered) list.
        divider_sections: set[str] = set()
        first_header_seen = False
        for _, cmd, _, desc in entries:
            if cmd is None:
                if first_header_seen:
                    divider_sections.add(desc)
                else:
                    first_header_seen = True

        prev_cmd: str | None = None
        for i, (_, cmd, arg, desc) in enumerate(entries):
            next_entry = entries[i + 1] if i + 1 < len(entries) else None
            needs_end_section = (
                next_entry is not None
                and next_entry[1] is None
                and next_entry[3] in divider_sections
            )
            if cmd is None:
                table.add_row(f"[bold yellow]{desc}[/bold yellow]", "", "")
                prev_cmd = None
            elif cmd == _NOTE:
                table.add_row("", "", desc)
            else:
                cmd_cell = cmd if cmd != prev_cmd else ""
                arg_cell = arg if arg is not None else ""
                table.add_row(cmd_cell, arg_cell, desc, end_section=needs_end_section)
                prev_cmd = cmd

        return table

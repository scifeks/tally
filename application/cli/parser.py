"""CLI argument parser for Tally."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the complete CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="tally",
        description="Security auditing platform with web UI and CLI",
    )

    parser.add_argument(
        "--base-path",
        default=".",
        metavar="DIR",
        help="Base directory for projects (default: current directory)",
    )
    parser.add_argument(
        "--project",
        type=str,
        metavar="NAME",
        help="Project name (optional if using REPL)",
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Command to execute"
    )

    _build_scan_command(subparsers)
    _build_run_command(subparsers)
    _build_report_command(subparsers)
    _build_triage_command(subparsers)
    _build_purge_command(subparsers)
    _build_stats_command(subparsers)
    _build_ui_command(subparsers)

    return parser


def _build_scan_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    scan = subparsers.add_parser("scan", help="Run security scans on repositories")
    scan.add_argument(
        "--repo",
        type=str,
        metavar="REPOS",
        help="Comma-separated repository names to scan",
    )

    tool_group = scan.add_mutually_exclusive_group()
    tool_group.add_argument(
        "--tool",
        type=str,
        metavar="TOOLS",
        help="Comma-separated tools to use (overrides defaults)",
    )
    tool_group.add_argument(
        "--skip-tools",
        type=str,
        metavar="TOOLS",
        help="Comma-separated tools to exclude",
    )

    scan.add_argument(
        "--domain",
        type=str,
        metavar="DOMAINS",
        help="Comma-separated domains to scan (for DAST tools)",
    )
    scan.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip enrichment step after scanning",
    )


def _build_run_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    run = subparsers.add_parser("run", help="Run a single tool directly")
    run.add_argument(
        "tool",
        type=str,
        help="Tool name to run",
    )
    run.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout in seconds",
    )
    run.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Raw arguments passed to the tool",
    )


def _build_report_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    report = subparsers.add_parser("report", help="Generate security reports")
    report.add_argument(
        "--format",
        default="pdf",
        choices=["pdf", "markdown", "html", "json"],
        help="Report format (default: pdf)",
    )
    report.add_argument(
        "--output",
        type=str,
        metavar="PATH",
        help="Output file path",
    )
    report.add_argument(
        "--testing-type",
        default="white_box",
        choices=["white_box", "grey_box", "black_box"],
        help="Testing type for report (default: white_box)",
    )
    report.add_argument(
        "--engagement-date",
        type=str,
        metavar="DATE",
        help="Engagement date (YYYY-MM-DD format)",
    )

    report_subparsers = report.add_subparsers(
        dest="report_command",
        required=False,
        help="Report sub-command (default: full report)",
    )

    draft_parser = report_subparsers.add_parser(
        "draft", help="Generate a draft report section"
    )
    draft_parser.add_argument(
        "section",
        nargs="?",
        type=str,
        help="Report section to draft",
    )
    draft_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing draft",
    )
    draft_parser.add_argument(
        "--skip-triage",
        action="store_true",
        help="Skip triage before drafting",
    )

    shell_parser = report_subparsers.add_parser(
        "shell", help="Generate a shell PDF with placeholders"
    )
    shell_parser.add_argument(
        "--testing-type",
        default="white_box",
        choices=["white_box", "grey_box", "black_box"],
        help="Testing type for shell (default: white_box)",
    )
    shell_parser.add_argument(
        "--engagement-date",
        type=str,
        metavar="DATE",
        help="Engagement date (YYYY-MM-DD format)",
    )
    shell_parser.add_argument(
        "--output",
        type=str,
        metavar="PATH",
        help="Output file path",
    )


def _build_triage_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    triage = subparsers.add_parser("triage", help="Triage and classify findings")
    triage.add_argument(
        "--batch",
        action="store_true",
        help="Run in batch mode (non-interactive)",
    )
    triage.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate triage without saving changes",
    )
    triage.add_argument(
        "--rebuild-container",
        action="store_true",
        help="Rebuild triage container before running",
    )


def _build_purge_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    purge = subparsers.add_parser("purge", help="Delete findings or scan results")
    purge.add_argument(
        "--tool",
        type=str,
        metavar="TOOLS",
        help="Comma-separated tools to purge results from",
    )
    purge.add_argument(
        "--keep-reports",
        action="store_true",
        help="Preserve generated reports",
    )


def _build_stats_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    subparsers.add_parser("stats", help="Display project statistics")


def _build_ui_command(
    subparsers: argparse._SubParsersAction,  # type: ignore
) -> None:
    ui = subparsers.add_parser("ui", help="Launch the web interface")
    ui_subparsers = ui.add_subparsers(
        dest="ui_command", required=True, help="UI sub-command"
    )
    ui_subparsers.add_parser("serve", help="Start the web server")

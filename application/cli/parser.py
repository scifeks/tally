"""CLI argument parser for Tally."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the complete CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="tally",
        description="Security auditing platform with web UI and CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  tally --project myapp --command scan"
            " --tool semgrep\n"
            "  tally --project myapp --command scan"
            " --skip-tools gitleaks --skip-enrichment\n"
            "  tally --project myapp --command run"
            " --tool semgrep --timeout 300\n"
            "  tally --project myapp --command report"
            " --format pdf\n"
            "  tally --project myapp --command report"
            " --type draft --section executive_summary\n"
            "  tally --project myapp --command triage"
            " --batch\n"
            "  tally --project myapp --command purge"
            " --tool semgrep --keep-reports\n"
            "  tally --project myapp --command stats\n"
            "  tally --project myapp --command"
            " integration-sync\n"
            "  tally --command ui"
        ),
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
        help="Project name",
    )
    parser.add_argument(
        "--command",
        required=True,
        choices=[
            "scan",
            "run",
            "report",
            "triage",
            "purge",
            "stats",
            "integration-sync",
            "ui",
        ],
        help="Command to execute",
    )

    tool_group = parser.add_mutually_exclusive_group()
    tool_group.add_argument(
        "--tool",
        type=str,
        metavar="TOOLS",
        help=(
            "Comma-separated tool names "
            "(scan: override defaults, purge: target, run: execute)"
        ),
    )
    tool_group.add_argument(
        "--skip-tools",
        type=str,
        metavar="TOOLS",
        help="Comma-separated tools to exclude (scan only)",
    )

    parser.add_argument(
        "--repo",
        type=str,
        metavar="REPOS",
        help="Comma-separated repository names to scan",
    )
    parser.add_argument(
        "--domain",
        type=str,
        metavar="DOMAINS",
        help="Comma-separated domains to scan (for DAST tools)",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip enrichment step after scanning",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout in seconds (run only)",
    )

    parser.add_argument(
        "--type",
        choices=["draft", "final", "shell"],
        default=None,
        help="Report type: draft, final, shell (default: final)",
    )
    parser.add_argument(
        "--format",
        default="pdf",
        choices=["pdf", "markdown", "html", "json"],
        help="Report format (default: pdf)",
    )
    parser.add_argument(
        "--output",
        type=str,
        metavar="PATH",
        help="Output file path",
    )
    parser.add_argument(
        "--testing-type",
        default="white_box",
        choices=["white_box", "grey_box", "black_box"],
        help="Testing type for report (default: white_box)",
    )
    parser.add_argument(
        "--engagement-date",
        type=str,
        metavar="DATE",
        help="Engagement date (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--section",
        type=str,
        help="Report section to draft",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing draft",
    )
    parser.add_argument(
        "--skip-triage",
        action="store_true",
        help="Skip triage before drafting",
    )

    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run in batch mode (non-interactive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate triage without saving changes",
    )
    parser.add_argument(
        "--rebuild-container",
        action="store_true",
        help="Rebuild triage container before running",
    )

    parser.add_argument(
        "--keep-reports",
        action="store_true",
        help="Preserve generated reports",
    )

    parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        metavar="ID",
        help="Scan run ID to export (integration-sync only)",
    )

    parser.add_argument(
        "--engagement-type",
        type=str,
        default=None,
        metavar="TYPE",
        help="Engagement type override (integration-sync only)",
    )

    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Pass-through arguments for the tool (run only)",
    )

    return parser

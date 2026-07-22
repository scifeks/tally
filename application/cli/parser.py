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
            "  tally --command ui\n"
            "  tally --command project-create"
            " --company-name ACME --department-name Engineering\n"
            "  tally --command project-list\n"
            "  tally --project myapp --command repo-add"
            " --repo-name backend --repo-path ./\n"
            "  tally --project myapp --command repo-list\n"
            "  tally --project myapp --command repo-edit"
            " --repo-name backend --languages python,go\n"
            "  tally --project myapp --command repo-delete"
            " --repo-name backend"
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
            "project-create",
            "project-list",
            "repo-add",
            "repo-list",
            "repo-edit",
            "repo-delete",
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
        "--since-commit",
        type=str,
        metavar="COMMIT",
        help="Scan only files changed since this commit",
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
        "--company-name",
        type=str,
        default="",
        metavar="NAME",
        help="Company name (project-create only)",
    )
    parser.add_argument(
        "--department-name",
        type=str,
        default="",
        metavar="NAME",
        help="Department name (project-create only)",
    )
    parser.add_argument(
        "--abbreviation",
        type=str,
        default="",
        metavar="CODE",
        help="Project abbreviation, max 3 chars (project-create only)",
    )

    parser.add_argument(
        "--repo-name",
        type=str,
        metavar="NAME",
        help="Repository name (repo-add, repo-edit, repo-delete)",
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        metavar="PATH",
        help="Filesystem path to repository (repo-add)",
    )
    parser.add_argument(
        "--languages",
        type=str,
        metavar="LANGS",
        help="Comma-separated languages (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--repo-type",
        type=str,
        metavar="TYPES",
        help=("Comma-separated service types: library, api, ui (repo-add, repo-edit)"),
    )
    parser.add_argument(
        "--base-urls",
        type=str,
        metavar="URLS",
        help="Comma-separated base URLs for DAST tools (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--graphql-paths",
        type=str,
        metavar="PATHS",
        help=("Comma-separated GraphQL endpoint paths (repo-add, repo-edit)"),
    )
    parser.add_argument(
        "--container-name",
        type=str,
        metavar="NAME",
        help="Docker container name (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--docker-path",
        type=str,
        metavar="PATH",
        help="Container mount path (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--dependencies-file",
        type=str,
        metavar="PATH",
        help=("Dependencies file path for supply-chain scanning (repo-add, repo-edit)"),
    )
    parser.add_argument(
        "--test-dirs",
        type=str,
        metavar="DIRS",
        help="Comma-separated test directory names (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--ignore-dirs",
        type=str,
        metavar="DIRS",
        help="Comma-separated directory names to exclude (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--no-crawl",
        action="store_true",
        help="Disable Katana/Noir crawling for this repo (repo-add, repo-edit)",
    )
    parser.add_argument(
        "--psalm-stubs",
        type=str,
        metavar="STUBS",
        help=("Comma-separated Psalm stub packages (repo-add, repo-edit)"),
    )
    parser.add_argument(
        "--graphql-cop-headers",
        type=str,
        metavar="JSON",
        help=("JSON string of HTTP headers for graphql-cop (repo-add, repo-edit)"),
    )

    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Pass-through arguments for the tool (run only)",
    )

    return parser

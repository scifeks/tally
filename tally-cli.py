#!/usr/bin/env python3
"""Non-interactive CLI entry point for tally security auditing."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.exit_codes import GENERAL_ERROR, PROJECT_NOT_FOUND
from application.cli.parser import build_parser

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.tools.registry import ToolRegistry


def _check_attestation(base_path: str) -> bool:
    from core.config.manager import ConfigManager

    return ConfigManager(base_path).global_config.location_attestation_confirmed


def _setup_logging() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    main_handler = logging.FileHandler(
        logs_dir / f"{date.today()}.log", encoding="utf-8"
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.addFilter(lambda r: r.levelno < logging.ERROR)
    main_handler.setFormatter(fmt)

    err_handler = logging.FileHandler(
        logs_dir / f"errors-{date.today()}.log", encoding="utf-8"
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.DEBUG, handlers=[main_handler, err_handler])


def _dispatch(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: str,
) -> int:
    """Route to the appropriate command handler."""
    from application.cli.commands.purge import cmd_purge
    from application.cli.commands.report import cmd_report
    from application.cli.commands.run import cmd_run
    from application.cli.commands.scan import cmd_scan
    from application.cli.commands.stats import cmd_stats
    from application.cli.commands.triage import cmd_triage
    from application.cli.commands.ui import cmd_ui

    handlers = {
        "scan": cmd_scan,
        "run": cmd_run,
        "report": cmd_report,
        "triage": cmd_triage,
        "purge": cmd_purge,
        "stats": cmd_stats,
        "ui": cmd_ui,
    }

    handler = handlers.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return GENERAL_ERROR

    return handler(args, project_registry, tool_registry, Path(base_path))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    base_path = args.base_path

    if not _check_attestation(base_path):
        print(
            "Location attestation not confirmed. "
            "Run the interactive REPL (python3 tally.py) first "
            "to complete the attestation.",
            file=sys.stderr,
        )
        return GENERAL_ERROR

    _setup_logging()

    from application.bootstrap import BootstrapService
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.tools.registry import ToolRegistry
    from infrastructure.store.project_registry import (
        ProjectRegistryRepository,
    )

    registry_repo = ProjectRegistryRepository(Path(base_path) / "tally.db")
    project_registry = ProjectRegistryService(registry_repo)
    tool_registry = ToolRegistry()

    BootstrapService(
        registry_repo=registry_repo,
        project_registry=project_registry,
        tool_registry=tool_registry,
        base_path=base_path,
    ).run()

    needs_project = args.command not in ("ui",)
    is_rebuild = args.command == "triage" and getattr(args, "rebuild_container", False)
    if needs_project and not is_rebuild:
        if not args.project:
            print(
                "Error: --project is required for this command.",
                file=sys.stderr,
            )
            return PROJECT_NOT_FOUND

    return _dispatch(args, project_registry, tool_registry, base_path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(GENERAL_ERROR)

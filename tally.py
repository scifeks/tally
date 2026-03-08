#!/usr/bin/env python3
"""Main entry point for tally pentesting REPL."""

import argparse
import sys
from pathlib import Path

from core.repl import REPL
from core.startup.checker import DependencyChecker
from core.tools import tool_registry
from core.tools.registry import discover_tools

_BASE_PATH = "."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tally pentesting REPL")
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip dependency checks on startup (for development)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run dependency checks and exit without starting the REPL",
    )
    args = parser.parse_args()

    # First-run setup: generate commands.json if absent.
    # Runs before --check and --skip-checks so the registry is always current.
    if not (Path(_BASE_PATH) / "config" / "commands.json").exists():
        from core.setup.commands_setup import run_commands_setup

        run_commands_setup(_BASE_PATH)

    # Re-run discovery with the confirmed base_path so the registry reflects
    # whatever commands.json now contains (the module-level auto-discovery in
    # registry.py ran at import time before setup completed).
    discover_tools(_BASE_PATH)

    checker = DependencyChecker(tool_registry)

    if args.check:
        result = checker.run()
        sys.exit(0 if result.all_required_present else 1)

    if not args.skip_checks:
        result = checker.run()
        if not result.all_required_present:
            sys.exit(1)

    try:
        REPL(base_path=_BASE_PATH).run()
    except KeyboardInterrupt:
        pass

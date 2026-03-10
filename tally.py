#!/usr/bin/env python3
"""Main entry point for tally security auditing REPL."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from core.repl import REPL
from core.startup.checker import DependencyChecker
from core.tools import tool_registry
from core.tools.registry import discover_tools

_BASE_PATH = "."

_ATTESTATION_TEXT = """
This tool is not licensed for use in California or Colorado due to
state-specific regulatory requirements (CA Age-Appropriate Design Code,
CO Privacy Act). By continuing, you attest that you are not accessing
this tool from either of those states.

Continue? [y/N]: """


def check_location_attestation(base_path: str) -> None:
    from core.config.manager import ConfigManager

    config_manager = ConfigManager(base_path)
    if config_manager.global_config.location_attestation_confirmed:
        return
    answer = input(_ATTESTATION_TEXT).strip().lower()
    if answer != "y":
        sys.exit(0)
    config_manager.global_config.location_attestation_confirmed = True
    config_manager.save_global_config(config_manager.global_config)


if __name__ == "__main__":
    check_location_attestation(_BASE_PATH)
    # --- logging setup (first thing after attestation, before any module does work) ---
    _logs_dir = Path("logs")
    _logs_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=_logs_dir / f"{date.today()}.log",
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        encoding="utf-8",
    )
    # ---------------------------------------------------------------

    parser = argparse.ArgumentParser(description="Tally security auditing REPL")
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

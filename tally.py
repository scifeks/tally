#!/usr/bin/env python3
"""Main entry point for tally security auditing REPL."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from application.project.registry_service import ProjectRegistryService
from application.repl import REPL
from application.runtime import RuntimeDependencyService
from application.startup.checker import DependencyChecker
from application.tools.registry import discover_tools
from infrastructure.runtime import ClaudeCodeProbe
from infrastructure.store.project_registry import ProjectRegistryRepository

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


def _build_project_registry(base_path: str) -> ProjectRegistryService:
    repo = ProjectRegistryRepository(Path(base_path) / "tally.db")
    repo.init_schema()
    svc = ProjectRegistryService(repo)
    svc.sync(base_path)
    return svc


if __name__ == "__main__":
    # Parse args first so --base-path is available for attestation and setup.
    parser = argparse.ArgumentParser(description="Tally security auditing REPL")
    parser.add_argument(
        "--base-path",
        default=_BASE_PATH,
        metavar="DIR",
        help="Root directory for config, projects, and logs (default: .)",
    )
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
    _BASE_PATH = args.base_path

    check_location_attestation(_BASE_PATH)
    # --- logging setup (first thing after attestation, before any module does work) ---
    _logs_dir = Path("logs")
    _logs_dir.mkdir(exist_ok=True)
    _log_fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _main_handler = logging.FileHandler(
        _logs_dir / f"{date.today()}.log", encoding="utf-8"
    )
    _main_handler.setLevel(logging.DEBUG)
    _main_handler.addFilter(lambda r: r.levelno < logging.ERROR)
    _main_handler.setFormatter(_log_fmt)

    _err_handler = logging.FileHandler(
        _logs_dir / f"errors-{date.today()}.log", encoding="utf-8"
    )
    _err_handler.setLevel(logging.ERROR)
    _err_handler.setFormatter(_log_fmt)

    logging.basicConfig(level=logging.DEBUG, handlers=[_main_handler, _err_handler])
    # ---------------------------------------------------------------

    # First-run setup: generate commands.json if absent.
    # Runs before --check and --skip-checks so the registry is always current.
    if not (Path(_BASE_PATH) / "config" / "commands.json").exists():
        from application.setup.commands_setup import run_commands_setup

        run_commands_setup(_BASE_PATH)

    # Phase 9.1: clear stale .tmp files left behind by interrupted atomic
    # writes from a prior crash. Idempotent and bounded to config dirs.
    from core.config._atomic import sweep_orphans

    sweep_orphans(Path(_BASE_PATH))

    # Re-run discovery with the confirmed base_path so the registry reflects
    # whatever commands.json now contains (the module-level auto-discovery in
    # registry.py ran at import time before setup completed).
    discover_tools(_BASE_PATH)

    runtime_service = RuntimeDependencyService([ClaudeCodeProbe()])

    if args.check:
        result = DependencyChecker(runtime_service=runtime_service).run()
        sys.exit(0 if result.all_required_present else 1)

    if not args.skip_checks:
        result = DependencyChecker().run(silent=True)
        if not result.all_required_present:
            sys.exit(1)

    # Build the project registry (creates tally.db on first run, syncs from disk).
    project_registry = _build_project_registry(_BASE_PATH)

    # Phase 9.2: stamp uuids into project.json + populate the per-project
    # ``repositories`` table + backfill ``findings.repo_id``. Idempotent.
    from application.project.repository_sync import (
        sync_repositories_for_all_projects,
    )

    sync_repositories_for_all_projects(_BASE_PATH)

    try:
        REPL(
            base_path=_BASE_PATH,
            runtime_service=runtime_service,
            project_registry=project_registry,
        ).run()
    except KeyboardInterrupt:
        pass

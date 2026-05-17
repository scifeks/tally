#!/usr/bin/env python3
"""Main entry point for tally security auditing REPL."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from rich.console import Console

from application.bootstrap import BootstrapService
from application.project.registry_service import ProjectRegistryService
from application.repl import REPL
from application.repl.adapters.dependency_summary_display import (
    print_dependency_summary,
)
from application.runtime import (
    RuntimeDependencyService,
    build_runtime_dependency_probes,
)
from application.startup.checker import DependencyChecker
from application.tools.registry import ToolRegistry
from infrastructure.store.project_registry import ProjectRegistryRepository
from infrastructure.web_ui.runner import WebUiRunner

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

    runtime_service = RuntimeDependencyService(
        build_runtime_dependency_probes(base_path=_BASE_PATH)
    )

    if args.check:
        result = DependencyChecker(runtime_service=runtime_service).run()
        print_dependency_summary(Console(), result)
        sys.exit(0 if result.all_required_present else 1)

    if not args.skip_checks:
        result = DependencyChecker().run()
        if not result.all_required_present:
            sys.exit(1)

    registry_repo = ProjectRegistryRepository(Path(_BASE_PATH) / "tally.db")
    project_registry = ProjectRegistryService(registry_repo)
    tool_registry = ToolRegistry()

    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.runs import RunRepository

    BootstrapService(
        registry_repo=registry_repo,
        project_registry=project_registry,
        tool_registry=tool_registry,
        base_path=_BASE_PATH,
        run_repo_factory=lambda p: RunRepository(ConnectionFactory(p)),
    ).run()

    try:
        REPL(
            base_path=_BASE_PATH,
            runtime_service=runtime_service,
            project_registry=project_registry,
            web_ui_runner=WebUiRunner(),
            tool_registry=tool_registry,
        ).run()
    except KeyboardInterrupt:
        pass

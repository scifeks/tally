"""UI command handler for the Tally CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.exit_codes import SUCCESS
from core.config.manager import ConfigManager
from infrastructure.web_ui.runner import WebUiRunner

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_ui(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Launch the web UI server."""
    del args
    cfg = ConfigManager(str(base_path)).global_config
    WebUiRunner().serve(
        base_path=str(base_path),
        host=cfg.web_ui_host,
        api_port=cfg.web_ui_port,
        vite_port=cfg.web_ui_vite_port,
        allowed_origins=cfg.effective_allowed_origins,
        project_registry=project_registry,
        tool_registry=tool_registry,
    )
    return SUCCESS

"""REPL commands for the web UI dev server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.web_ui_runner import WebUiRunnerPort
    from application.repl.interface import REPL


class UiCommands:
    """Handlers for the `ui` REPL command."""

    def __init__(self, repl: REPL, web_ui_runner: WebUiRunnerPort) -> None:
        self._repl = repl
        self._web_ui_runner = web_ui_runner

    def cmd_ui(self, _cmd: str, args: list[str]) -> None:
        """ui <subcommand>: manage the web UI dev server."""
        if not args:
            self._show_help()
            return
        sub = args[0].lower()
        if sub == "serve":
            self.cmd_serve(args[1:])
        else:
            print(f"Unknown subcommand: {sub}")
            self._show_help()

    def _show_help(self) -> None:
        print("ui serve   Start FastAPI + Vite dev server, open browser")

    def cmd_serve(self, _args: list[str]) -> None:
        """Start the FastAPI API server and Vite dev server.

        The web UI is multi-project: the user picks a project in the SPA
        after the server is up. No active REPL project is required.

        Press Ctrl+C to stop the server.
        """
        cfg = self._repl.config.global_config
        self._web_ui_runner.serve(
            base_path=self._repl.base_path,
            host=cfg.web_ui_host,
            api_port=cfg.web_ui_port,
            vite_port=cfg.web_ui_vite_port,
            allowed_origins=cfg.effective_allowed_origins,
            project_registry=self._repl.project_registry,
            tool_registry=self._repl.tool_registry,
        )

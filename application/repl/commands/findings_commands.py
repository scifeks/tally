"""REPL commands for the findings web UI."""

from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from typing import TYPE_CHECKING

import web.server as web_server

if TYPE_CHECKING:
    from application.repl.interface import REPL


class FindingsCommands:
    """Handlers for the findings web UI command."""

    def __init__(self, repl: REPL) -> None:
        self._repl = repl

    def cmd_findings(self, _cmd: str, args: list[str]) -> None:
        """findings [visualize] — web UI for reviewing findings."""
        if not args:
            self._show_help()
            return
        sub = args[0].lower()
        if sub == "visualize":
            self.cmd_visualize(args[1:])
        else:
            print(f"Unknown subcommand: {sub}")
            self._show_help()

    def _show_help(self) -> None:
        print(
            "findings visualize    "
            "Launch the web UI for reviewing findings in a browser"
        )

    def cmd_visualize(self, _args: list[str]) -> None:
        """Start the web UI server and open a browser."""
        if not (project_name := self._repl.active_project):
            print(
                "No active project. Run `project add <name>` or "
                "`project select <name>` first."
            )
            return

        base_path: str = self._repl.base_path

        port = 8080
        try:
            with open(self._repl.config.global_config_path) as f:
                data = json.load(f)
            port = int(data.get("web_ui_port", 8080))
        except Exception:
            port = 8080

        token = secrets.token_hex(16)

        thread = threading.Thread(
            target=web_server.start,
            args=(base_path, project_name, port, token),
            daemon=True,
        )
        thread.start()

        time.sleep(0.5)
        if not thread.is_alive():
            print(f"Port {port} is already in use. The server may already be running.")
            return

        url = f"http://localhost:{port}/?token={token}"
        print(f"\nTally Web UI is running at:\n  {url}\n")
        webbrowser.open(url)
        print("Server running — press Ctrl+C to exit the REPL and stop the server.")

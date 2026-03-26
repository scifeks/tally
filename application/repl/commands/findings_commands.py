"""REPL commands for the findings web UI."""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time
import webbrowser
from typing import TYPE_CHECKING

import uvicorn

import web.server as web_server

if TYPE_CHECKING:
    from application.repl.interface import REPL


class FindingsCommands:
    """Handlers for the findings web UI command."""

    def __init__(self, repl: REPL) -> None:
        self._repl = repl
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

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
        print("findings visualize         Launch the web UI for reviewing findings")
        print("findings visualize --stop  Stop the running web UI server")

    def cmd_visualize(self, args: list[str]) -> None:
        """Start the web UI server and open a browser, or stop it."""
        if "--stop" in args:
            self._cmd_stop()
            return

        if not (project_name := self._repl.active_project):
            print(
                "No active project. Run `project add <name>` or "
                "`project select <name>` first."
            )
            return

        if self._server is not None:
            print(
                "Web UI server is already running. "
                "Use `findings visualize --stop` to stop it."
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

        server = web_server.create_server(base_path, project_name, port, token)
        self._server = server

        thread = threading.Thread(
            target=lambda: asyncio.run(server.serve()),
            daemon=True,
        )
        self._thread = thread
        thread.start()

        # Poll until the server begins accepting connections (up to 2 s).
        deadline = time.monotonic() + 2.0
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)

        if not server.started:
            self._server = None
            self._thread = None
            print(f"Port {port} is already in use or server failed to start.")
            return

        url = f"http://localhost:{port}/?token={token}"
        print(f"\nTally Web UI is running at:\n  {url}\n")
        # webbrowser.open() can block on Linux — run in its own daemon thread.
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        print("Server running — use `findings visualize --stop` to stop the server.")

    def _cmd_stop(self) -> None:
        """Stop the running web UI server."""
        if self._server is None:
            print("No web UI server is currently running.")
            return
        self._server.should_exit = True
        self._server = None
        self._thread = None
        print("Web UI server stopped.")

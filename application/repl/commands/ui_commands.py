"""REPL commands for the web UI dev server."""

from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

if TYPE_CHECKING:
    from application.repl.interface import REPL

ServerFactory = Callable[[str, str, int, str, str, list[str]], uvicorn.Server]

_BANNED_HOSTS = {"0.0.0.0", "::", ""}


class UiCommands:
    """Handlers for the `ui` REPL command."""

    def __init__(self, repl: REPL, server_factory: ServerFactory) -> None:
        self._repl = repl
        self._server_factory = server_factory
        self._server: uvicorn.Server | None = None
        self._api_thread: threading.Thread | None = None
        self._vite_proc: subprocess.Popen[bytes] | None = None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def cmd_ui(self, _cmd: str, args: list[str]) -> None:
        """ui <subcommand> — manage the web UI dev server."""
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
        print("ui serve         Start FastAPI + Vite dev server, open browser")
        print("ui serve --stop  Stop the running servers")

    # ------------------------------------------------------------------
    # `ui serve`
    # ------------------------------------------------------------------

    def cmd_serve(self, args: list[str]) -> None:
        """Start (or stop) the FastAPI API server and Vite dev server."""
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
            print("UI servers are already running. Use `ui serve --stop` to stop them.")
            return

        cfg = self._repl.config.global_config
        host: str = cfg.web_ui_host
        api_port: int = cfg.web_ui_port
        vite_port: int = cfg.web_ui_vite_port
        allowed_origins: list[str] = cfg.effective_allowed_origins

        if host in _BANNED_HOSTS:
            print(
                f"web_ui_host {host!r} would bind to all interfaces. "
                "Set an explicit IP or hostname in config/global.json."
            )
            return

        base_path: str = self._repl.base_path
        ui_dir = Path(base_path) / "ui"

        if not ui_dir.is_dir():
            print(f"UI directory not found: {ui_dir}")
            return

        self._write_env_local(ui_dir, host, api_port, vite_port)

        token = secrets.token_hex(16)
        server = self._server_factory(
            base_path, project_name, api_port, token, host, allowed_origins
        )
        self._server = server

        api_thread = threading.Thread(
            target=lambda: asyncio.run(server.serve()),
            daemon=True,
        )
        self._api_thread = api_thread
        api_thread.start()

        deadline = time.monotonic() + 2.0
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)

        if not server.started:
            self._server = None
            self._api_thread = None
            print(f"Port {api_port} is already in use or API server failed to start.")
            return

        self._start_vite(ui_dir)

        vite_url = f"http://{host}:{vite_port}"
        if not self._wait_for_port(host, vite_port, timeout=10.0):
            print(
                f"Vite dev server did not become ready within 10 s. "
                f"Try opening {vite_url} manually."
            )
        else:
            import webbrowser

            browser_url = f"{vite_url}/?h={token}"
            print(f"\nTally Web UI is running at:\n  {browser_url}\n")
            threading.Thread(
                target=webbrowser.open, args=(browser_url,), daemon=True
            ).start()

        print("Servers running — use `ui serve --stop` to stop.")

    def _cmd_stop(self) -> None:
        """Stop the running servers."""
        stopped_any = False
        if self._server is not None:
            self._server.should_exit = True
            self._server = None
            self._api_thread = None
            stopped_any = True
        if self._vite_proc is not None:
            try:
                self._vite_proc.terminate()
                self._vite_proc.wait(timeout=5)
            except Exception:
                self._vite_proc.kill()
            self._vite_proc = None
            stopped_any = True
        if stopped_any:
            print("UI servers stopped.")
        else:
            print("No UI servers are currently running.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_env_local(
        ui_dir: Path,
        host: str,
        api_port: int,
        vite_port: int,
    ) -> None:
        """Atomically write ui/.env.local with Tally's config values."""
        content = (
            f"TALLY_HOST={host}\n"
            f"TALLY_VITE_PORT={vite_port}\n"
            f"VITE_API_BASE_URL=http://{host}:{api_port}\n"
        )
        target = ui_dir / ".env.local"
        tmp = target.with_suffix(".env.local.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)

    def _start_vite(self, ui_dir: Path) -> None:
        npm = "npm"
        env = {**os.environ, "FORCE_COLOR": "0"}
        try:
            self._vite_proc = subprocess.Popen(
                [npm, "run", "dev"],
                cwd=ui_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("npm not found — Vite dev server not started.")
            self._vite_proc = None

    @staticmethod
    def _wait_for_port(host: str, port: int, timeout: float) -> bool:
        """Return True once a TCP connection to host:port succeeds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.25)
        return False

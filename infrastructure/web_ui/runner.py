"""WebUiRunner: concrete WebUiRunnerPort that launches the embedded dev UI.

Composes the FastAPI app factory from `web.server`, spawns the Vite dev
server, opens the browser, and runs uvicorn until the user hits Ctrl+C.
The REPL holds this adapter behind `WebUiRunnerPort` and never imports
fastapi, uvicorn, or web/ directly.
"""

from __future__ import annotations

import atexit
import os
import secrets
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from application.ports.web_ui_runner import WebUiRunnerPort
from web.server import create_web_app

_BANNED_HOSTS = {"0.0.0.0", "::", ""}


class WebUiRunner(WebUiRunnerPort):
    """Drive the embedded FastAPI + Vite dev environment for `ui serve`."""

    def __init__(self) -> None:
        self._vite_proc: subprocess.Popen[bytes] | None = None

    def serve(
        self,
        *,
        base_path: str,
        host: str,
        api_port: int,
        vite_port: int,
        allowed_origins: list[str],
    ) -> None:
        if host in _BANNED_HOSTS:
            print(
                f"web_ui_host {host!r} would bind to all interfaces. "
                "Set an explicit IP or hostname in config/global.json."
            )
            return

        ui_dir = Path(base_path) / "ui"
        if not ui_dir.is_dir():
            print(f"UI directory not found: {ui_dir}")
            return

        self._write_env_local(ui_dir, host, api_port, vite_port)

        token = secrets.token_hex(16)
        app = create_web_app(base_path, api_port, token, allowed_origins)

        self._start_vite(ui_dir)

        vite_url = f"http://{host}:{vite_port}"
        if not self._wait_for_port(host, vite_port, timeout=10.0):
            print(
                f"Vite dev server did not become ready within 10 s. "
                f"Try opening {vite_url} manually."
            )
        else:
            browser_url = f"{vite_url}/?token={token}&fresh=1"
            print(f"\nTally Web UI is running at:\n  {browser_url}\n")
            threading.Thread(
                target=webbrowser.open, args=(browser_url,), daemon=True
            ).start()

        print("Press Ctrl+C to stop the server.")
        try:
            uvicorn.run(app, host=host, port=api_port, log_level="warning")
        except OSError:
            print(f"Port {api_port} is already in use or API server failed to start.")

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

    def _stop_vite(self) -> None:
        if self._vite_proc is None:
            return
        try:
            self._vite_proc.terminate()
            self._vite_proc.wait(timeout=5)
        except Exception:
            self._vite_proc.kill()
        self._vite_proc = None

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
            print("npm not found. Vite dev server not started.")
            self._vite_proc = None
            return
        atexit.register(self._stop_vite)

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

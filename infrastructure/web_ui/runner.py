"""WebUiRunner: concrete WebUiRunnerPort that launches the embedded dev UI."""

from __future__ import annotations

import atexit
import logging
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn

from application.ports.web_ui_runner import WebUiRunnerPort
from infrastructure.web_ui.tls import ensure_tls_cert

if TYPE_CHECKING:
    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_BANNED_HOSTS = {"0.0.0.0", "::", ""}


class WebUiRunner(WebUiRunnerPort):
    """Drive the embedded FastAPI + Vite dev environment for `ui serve`."""

    def __init__(self, app_factory: Callable[..., Any]) -> None:
        self._app_factory = app_factory
        self._vite_proc: subprocess.Popen[bytes] | None = None
        self._vite_log: Any | None = None
        self._shutting_down = False

    def serve(
        self,
        *,
        base_path: str,
        host: str,
        api_port: int,
        vite_port: int,
        allowed_origins: list[str],
        project_registry: ProjectRegistryService,
        tool_registry: ToolRegistry,
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

        cert_path, key_path = ensure_tls_cert(base_path, host)
        self._write_env_local(ui_dir, host, api_port, vite_port, cert_path, key_path)

        token = secrets.token_hex(16)
        app = self._app_factory(
            base_path,
            api_port,
            token,
            allowed_origins,
            host=host,
            project_registry=project_registry,
            tool_registry=tool_registry,
        )

        self._start_vite(ui_dir, Path(base_path))

        vite_url = f"https://{host}:{vite_port}"
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
            uvicorn.run(
                app,
                host=host,
                port=api_port,
                log_level="warning",
                ssl_keyfile=str(key_path),
                ssl_certfile=str(cert_path),
                timeout_graceful_shutdown=3,
            )
        except KeyboardInterrupt:
            pass
        except OSError:
            print(f"Port {api_port} is already in use or API server failed to start.")
        finally:
            self._stop_vite()

    @staticmethod
    def _write_env_local(
        ui_dir: Path,
        host: str,
        api_port: int,
        vite_port: int,
        cert_path: Path,
        key_path: Path,
    ) -> None:
        """Atomically write ui/.env.local with Tally's config values."""
        content = (
            f"TALLY_HOST={host}\n"
            f"TALLY_VITE_PORT={vite_port}\n"
            f"VITE_API_BASE_URL=https://{host}:{api_port}\n"
            f"TALLY_TLS_CERT={cert_path}\n"
            f"TALLY_TLS_KEY={key_path}\n"
        )
        target = ui_dir / ".env.local"
        tmp = target.with_suffix(".env.local.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)

    @staticmethod
    def _killpg_safe(pgid: object, sig: int) -> None:
        """Signal a process group, refusing group IDs that are not int > 1."""
        # MagicMock.__index__ returns 1; os.killpg(1, sig) is kill(-1, sig).
        if not isinstance(pgid, int) or isinstance(pgid, bool) or pgid <= 1:
            logger.error(
                "Refusing os.killpg(%r, %s): not a valid process group ID",
                pgid,
                sig,
            )
            return
        os.killpg(pgid, sig)

    def _stop_vite(self) -> None:
        if self._vite_proc is None:
            return
        self._shutting_down = True
        try:
            self._killpg_safe(self._vite_proc.pid, signal.SIGTERM)
            self._vite_proc.wait(timeout=5)
        except Exception:
            try:
                self._killpg_safe(self._vite_proc.pid, signal.SIGKILL)
            except OSError:
                pass
        self._vite_proc = None
        if self._vite_log is not None:
            self._vite_log.close()
            self._vite_log = None

    def _monitor_vite(self, log_path: Path) -> None:
        """Poll the Vite process and warn the user if it exits."""
        while self._vite_proc is not None:
            rc = self._vite_proc.poll()
            if rc is not None:
                if not self._shutting_down:
                    print(
                        f"\nVite dev server exited (code {rc}). "
                        f"The web UI will not load. "
                        f"Check {log_path} for details."
                    )
                return
            time.sleep(2)

    def _start_vite(self, ui_dir: Path, base_path: Path) -> None:
        npm = "npm"
        env = {**os.environ, "FORCE_COLOR": "0"}

        log_dir = base_path / "logs"
        log_dir.mkdir(exist_ok=True)
        log_name = "vite-" + datetime.now().strftime("%Y-%m-%d") + ".log"
        self._vite_log = open(log_dir / log_name, "a", encoding="utf-8")

        try:
            self._vite_proc = subprocess.Popen(
                [npm, "run", "dev"],
                cwd=ui_dir,
                env=env,
                stdout=self._vite_log,
                stderr=self._vite_log,
                start_new_session=True,
            )
        except FileNotFoundError:
            print("npm not found. Vite dev server not started.")
            self._vite_log.close()
            self._vite_log = None
            self._vite_proc = None
            return
        atexit.register(self._stop_vite)

        monitor = threading.Thread(
            target=self._monitor_vite,
            args=(log_dir / log_name,),
            daemon=True,
        )
        monitor.start()

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

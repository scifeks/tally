"""REPL commands for the web UI dev server."""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.web_ui.tls import regenerate_tls_cert, tls_paths

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
        elif sub == "ssl":
            self._cmd_ssl(args[1:])
        else:
            print(f"Unknown subcommand: {sub}")
            self._show_help()

    def _show_help(self) -> None:
        print("ui serve            Start FastAPI + Vite dev server")
        print("ui ssl regenerate   Regenerate the self-signed TLS certificate")

    def cmd_serve(self, _args: list[str]) -> None:
        """Start the HTTPS API server and Vite dev server."""
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

    def _cmd_ssl(self, args: list[str]) -> None:
        if not args or args[0].lower() != "regenerate":
            print("ui ssl regenerate   Regenerate the self-signed TLS certificate")
            return
        self._cmd_ssl_regenerate()

    def _cmd_ssl_regenerate(self) -> None:
        cfg = self._repl.config.global_config
        host = cfg.web_ui_host
        cert_path, key_path = tls_paths(self._repl.base_path)
        existed = cert_path.exists()

        print(f"Generating self-signed TLS certificate for {host}")
        regenerate_tls_cert(self._repl.base_path, host)

        label = "Regenerated" if existed else "Generated"
        print(f"{label}:")
        print(f"  Certificate: {cert_path}")
        print(f"  Private key: {key_path}")
        print(f"  SAN: {host}, localhost, 127.0.0.1")
        print(f"  Valid for: {365} days")
        if host != "127.0.0.1":
            print(
                "\nIf you change web_ui_host in config/global.json, "
                "run this command again."
            )

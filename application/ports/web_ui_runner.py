"""WebUiRunner port: launch the embedded web UI dev server.

Adapters:
  infrastructure/web_ui/runner.py::WebUiRunner

Owns the FastAPI app construction, uvicorn lifecycle, Vite dev-server
spawn, browser launch, and `.env.local` seed so the REPL no longer
imports web/, fastapi, or uvicorn.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WebUiRunnerPort(Protocol):
    """Start the embedded web UI dev server. Blocks until the user stops it."""

    def serve(
        self,
        *,
        base_path: str,
        host: str,
        api_port: int,
        vite_port: int,
        allowed_origins: list[str],
    ) -> None: ...

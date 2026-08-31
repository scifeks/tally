"""Track the active MCP server instance."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpServerHandle:
    host: str
    port: int
    source: str
    server: Any
    thread: threading.Thread


class McpServerRegistry:
    """Process-singleton for the running MCP server."""

    def __init__(self) -> None:
        self._handle: McpServerHandle | None = None
        self._lock = threading.Lock()

    def register(self, handle: McpServerHandle) -> None:
        with self._lock:
            if self._handle is not None:
                raise RuntimeError(
                    f"MCP server already running on port {self._handle.port}"
                )
            self._handle = handle

    def unregister(self) -> None:
        with self._lock:
            self._handle = None

    def get(self) -> McpServerHandle | None:
        with self._lock:
            return self._handle

    def is_active(self) -> bool:
        with self._lock:
            return self._handle is not None

    def reset(self) -> None:
        with self._lock:
            self._handle = None


_REGISTRY: McpServerRegistry | None = None


def get_mcp_server_registry() -> McpServerRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = McpServerRegistry()
    return _REGISTRY

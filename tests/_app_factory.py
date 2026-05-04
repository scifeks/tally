"""Shared helper for integration tests that need a fully-bootstrapped FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from application.bootstrap import BootstrapService
from application.project.registry_service import ProjectRegistryService
from application.tools.registry import ToolRegistry
from infrastructure.store.project_registry import ProjectRegistryRepository
from web.server import create_app


def build_test_app(
    base_path: Path,
    handshake_token: str,
    *,
    port: int,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    base = str(base_path)
    registry_repo = ProjectRegistryRepository(base_path / "tally.db")
    project_registry = ProjectRegistryService(registry_repo)
    tool_registry = ToolRegistry()
    BootstrapService(
        registry_repo=registry_repo,
        project_registry=project_registry,
        tool_registry=tool_registry,
        base_path=base,
    ).run()
    return create_app(
        base,
        handshake_token,
        port=port,
        project_registry=project_registry,
        tool_registry=tool_registry,
        allowed_origins=allowed_origins,
    )

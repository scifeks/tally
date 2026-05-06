"""Builds triage runners from config."""

from __future__ import annotations

from pathlib import Path

from application.config.mcp_defaults import load_mcp_defaults
from application.ports.triage_agent import TriageBackendFactoryPort, TriageBackendPort
from application.tools.registry import ToolRegistry
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.store import make_store

from .runner import _APP_ROOT, TriageRunner


class TriageProviderNotConfiguredError(RuntimeError):
    """Raised when triage is disabled."""


def load_triage_provider(*, app_root: Path | None = None) -> str:
    """Loads `triage_agent_provider`."""
    root = app_root or _APP_ROOT
    return ConfigManager(str(root)).global_config.triage_agent_provider


def ensure_triage_backend_configured(*, app_root: Path | None = None) -> str:
    """Returns the enabled triage provider."""
    provider = load_triage_provider(app_root=app_root)
    if provider == "":
        raise TriageProviderNotConfiguredError(
            "Triage is disabled. Set `triage_agent_provider` in config/global.json "
            "to `claude_code` or `open_code` to enable it."
        )
    return provider


class TriageAgentFactory(TriageBackendFactoryPort):
    """Builds the configured backend."""

    def __init__(self, *, app_root: Path | None = None) -> None:
        self._app_root = app_root or _APP_ROOT

    def create(self) -> TriageBackendPort:
        provider = ensure_triage_backend_configured(app_root=self._app_root)

        if provider == "claude_code":
            from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent

            return ClaudeTriageAgent()
        if provider == "open_code":
            from infrastructure.agents.opencode_triage_agent import OpenCodeTriageAgent

            return OpenCodeTriageAgent()
        raise RuntimeError(f"Unsupported triage agent provider: {provider!r}")


def build_triage_runner(
    project: str,
    tool_registry: ToolRegistry,
    *,
    app_root: Path | None = None,
    event_sink=None,
    cancel_token=None,
    project_id: int | None = None,
    scan_run_id: int | None = None,
    reset_for_resume_scan_run_id: int | None = None,
    triage_agent_factory: TriageBackendFactoryPort | None = None,
) -> TriageRunner:
    """Builds a runner with the configured backend."""
    root = app_root or _APP_ROOT
    paths = ProjectPaths.from_canonical(root, project)
    if not paths.findings_db.exists():
        raise FileNotFoundError(f"Project database not found: {paths.findings_db}")

    run_repo, _, triage_repo, audit_repo = make_store(root, project)
    if reset_for_resume_scan_run_id is not None:
        triage_repo.reset_for_resume(reset_for_resume_scan_run_id)
    _, _, session_timeout_seconds = load_mcp_defaults(str(root))
    agent_factory = triage_agent_factory or TriageAgentFactory(app_root=root)

    return TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        root,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        triage_backend=agent_factory.create(),
        session_timeout_seconds=session_timeout_seconds,
        tool_registry=tool_registry,
    )

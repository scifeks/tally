"""Builds triage runners from config."""

from __future__ import annotations

from pathlib import Path

from application.ports.triage_agent import OneshotTriageBackendPort
from application.tools.registry import ToolRegistry
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.store import make_store
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import (
    RepositoryRepository,
)

from .runner import TriageRunner


class TriageProviderNotConfiguredError(RuntimeError):
    """Raised when triage is disabled."""


def load_triage_provider(*, app_root: Path) -> str:
    """Loads `triage_agent_provider`."""
    return ConfigManager(str(app_root)).global_config.triage_agent_provider


def ensure_triage_backend_configured(*, app_root: Path) -> str:
    """Returns the enabled triage provider."""
    provider = load_triage_provider(app_root=app_root)
    if provider == "":
        raise TriageProviderNotConfiguredError(
            "Triage is disabled. Set `triage_agent_provider`"
            " in config/global.json"
            " to `claude_code` or `open_code` to enable it."
        )
    return provider


class TriageAgentFactory:
    """Builds the configured backend."""

    def __init__(self, *, app_root: Path) -> None:
        self._app_root = app_root

    def create(self) -> OneshotTriageBackendPort:
        provider = ensure_triage_backend_configured(app_root=self._app_root)

        from application.triage.compose import COMPOSE_RELATIVE_PATH

        compose_path = self._app_root / COMPOSE_RELATIVE_PATH

        if provider == "claude_code":
            from infrastructure.agents.claude_triage_agent import (
                ClaudeTriageAgent,
            )

            cfg = ConfigManager(str(self._app_root)).global_config
            model = cfg.claude.model if cfg.claude else "sonnet"
            return ClaudeTriageAgent(model=model, compose_path=compose_path)
        if provider == "open_code":
            from infrastructure.agents.opencode_triage_agent import (
                OpenCodeTriageAgent,
            )

            return OpenCodeTriageAgent(compose_path=compose_path)
        raise RuntimeError(f"Unsupported triage agent provider: {provider!r}")


def build_triage_runner(
    project: str,
    tool_registry: ToolRegistry,
    *,
    app_root: Path,
    event_sink=None,
    cancel_token=None,
    project_id: int | None = None,
    scan_run_id: int | None = None,
    reset_for_resume_scan_run_id: int | None = None,
) -> TriageRunner:
    """Builds a runner with the configured backend."""
    paths = ProjectPaths.from_canonical(app_root, project)
    if not paths.findings_db.exists():
        raise FileNotFoundError(f"Project database not found: {paths.findings_db}")

    run_repo, finding_repo, triage_repo, audit_repo = make_store(app_root, project)
    if reset_for_resume_scan_run_id is not None:
        triage_repo.reset_for_resume(reset_for_resume_scan_run_id)
    session_timeout_seconds = ConfigManager(
        str(app_root)
    ).global_config.triage_session_timeout_seconds

    factory = ConnectionFactory(paths.findings_db)
    repos = RepositoryRepository(factory).list_active()
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}

    provider = load_triage_provider(app_root=app_root)
    triaged_by = "claudecode" if provider == "claude_code" else "opencode"

    agent_factory = TriageAgentFactory(app_root=app_root)

    return TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        app_root,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        triage_backend=agent_factory.create(),
        session_timeout_seconds=session_timeout_seconds,
        tool_registry=tool_registry,
        finding_repo=finding_repo,
        repo_paths=repo_paths,
        triaged_by=triaged_by,
    )

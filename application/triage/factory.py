"""Builds triage runners from config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from application.ports.triage_agent import OneshotTriageBackendPort

if TYPE_CHECKING:
    from application.ports.audit_repository import (
        AuditRepositoryPort,
    )
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_batch_repository import (
        TriageBatchRepositoryPort,
    )
from application.tools.registry import ToolRegistry
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths

from .batching import MAX_FINDINGS_PER_BATCH
from .runner import TriageRunner


class TriageProviderNotConfiguredError(RuntimeError):
    """Raised when triage is disabled."""


@dataclass(frozen=True)
class ResolvedTriageConfig:
    provider_name: str
    base_url: str
    model: str
    timeout_seconds: int
    retry_count: int
    debug: bool


def resolve_triage_config(*, app_root: Path) -> ResolvedTriageConfig:
    """Merge provider config with triage_inference feature overrides."""
    cfg = ConfigManager(str(app_root)).global_config

    feature = cfg.triage_inference
    if feature is None:
        raise TriageProviderNotConfiguredError(
            "Triage is disabled. Set `triage_inference` "
            "in config/global.json to enable it. "
            'Example: {"provider": "ollama"}'
        )

    provider_name = feature.provider
    provider_config = getattr(cfg, provider_name, None)
    if provider_config is None:
        raise TriageProviderNotConfiguredError(
            f"Provider {provider_name!r} referenced by "
            "triage_inference is not configured in "
            "config/global.json"
        )

    merged = provider_config.model_dump()
    for key in (
        "base_url",
        "model",
        "timeout_seconds",
        "num_ctx",
        "max_tokens",
        "retry_count",
    ):
        val = getattr(feature, key, None)
        if val is not None:
            merged[key] = val

    return ResolvedTriageConfig(
        provider_name=provider_name,
        base_url=merged.get("base_url", ""),
        model=merged.get("model", ""),
        timeout_seconds=merged.get("timeout_seconds", 300),
        retry_count=merged.get("retry_count", 0),
        debug=feature.debug,
    )


def load_triage_provider(*, app_root: Path) -> str:
    """Returns the configured triage provider name.

    Reads from triage_inference.provider (preferred) or
    falls back to the legacy triage_agent_provider field.
    """
    cfg = ConfigManager(str(app_root)).global_config
    if cfg.triage_inference is not None:
        return cfg.triage_inference.provider
    return cfg.triage_agent_provider


def ensure_triage_backend_configured(*, app_root: Path) -> str:
    """Returns the enabled triage provider name."""
    provider = load_triage_provider(app_root=app_root)
    if provider == "":
        raise TriageProviderNotConfiguredError(
            "Triage is disabled. Set `triage_inference` "
            "in config/global.json to enable it."
        )
    return provider


class TriageAgentFactory:
    """Builds the configured triage backend adapter."""

    def __init__(self, *, app_root: Path) -> None:
        self._app_root = app_root

    def create(self) -> OneshotTriageBackendPort:
        resolved = resolve_triage_config(app_root=self._app_root)

        from application.triage.compose import (
            COMPOSE_RELATIVE_PATH,
        )

        compose_path = self._app_root / COMPOSE_RELATIVE_PATH

        if resolved.provider_name == "claude":
            from infrastructure.agents.claude_triage_agent import (
                ClaudeTriageAgent,
            )

            return ClaudeTriageAgent(
                model=resolved.model,
                compose_path=compose_path,
            )

        from infrastructure.agents.opencode_triage_agent import (
            OpenCodeTriageAgent,
        )

        return OpenCodeTriageAgent(
            compose_path=compose_path,
            model=resolved.model,
            provider_name=resolved.provider_name,
        )


def build_triage_runner(
    project: str,
    tool_registry: ToolRegistry,
    *,
    app_root: Path,
    run_repo: RunRepositoryPort,
    finding_repo: FindingRepositoryPort,
    triage_repo: TriageBatchRepositoryPort,
    audit_repo: AuditRepositoryPort,
    repo_paths: dict[str, Path],
    event_sink=None,
    cancel_token=None,
    project_id: int | None = None,
    scan_run_id: int | None = None,
    reset_for_resume_scan_run_id: int | None = None,
) -> TriageRunner:
    """Build a runner with the configured backend."""
    paths = ProjectPaths.from_canonical(app_root, project)
    if not paths.findings_db.exists():
        raise FileNotFoundError(f"Project database not found: {paths.findings_db}")

    if reset_for_resume_scan_run_id is not None:
        triage_repo.reset_for_resume(reset_for_resume_scan_run_id)

    resolved = resolve_triage_config(app_root=app_root)
    triaged_by = "claudecode" if resolved.provider_name == "claude" else "opencode"
    max_batch = MAX_FINDINGS_PER_BATCH if resolved.provider_name == "claude" else 1

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
        session_timeout_seconds=resolved.timeout_seconds,
        retry_count=resolved.retry_count,
        tool_registry=tool_registry,
        finding_repo=finding_repo,
        repo_paths=repo_paths,
        triaged_by=triaged_by,
        debug=resolved.debug,
        max_findings_per_batch=max_batch,
    )

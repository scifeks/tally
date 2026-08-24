"""LLM scan backend factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.llm_scan_backend import LlmScanBackendPort


def create_llm_scan_backend(
    *,
    app_root: Path,
    repo_paths: dict[str, Path],
) -> tuple[LlmScanBackendPort, int]:
    """Create an LLM scan backend and return (backend, timeout)."""
    from application.triage.compose import generate_triage_compose
    from application.triage.factory import resolve_triage_config

    resolved = resolve_triage_config(app_root=app_root)
    compose_path = generate_triage_compose(
        app_root,
        repo_paths,
        provider=resolved.provider_name,
        base_url=resolved.base_url,
        model=resolved.model,
    )

    if resolved.provider_name == "claude":
        from infrastructure.agents.claude_llm_scan_adapter import (
            ClaudeLlmScanAdapter,
        )

        backend: LlmScanBackendPort = ClaudeLlmScanAdapter(
            model=resolved.model,
            compose_path=compose_path,
        )
    else:
        from infrastructure.agents.opencode_llm_scan_adapter import (
            OpenCodeLlmScanAdapter,
        )

        backend = OpenCodeLlmScanAdapter(
            compose_path=compose_path,
            model=resolved.model,
            provider_name=resolved.provider_name,
        )

    return backend, resolved.timeout_seconds

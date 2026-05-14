"""DAST prerequisite resolution service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.detection.noir import noir_skip_reason
from domain.tools.constants import DAST_TOOLS, DISCOVERY_TOOLS

if TYPE_CHECKING:
    from core.config.schemas.repository import Repository


@dataclass(frozen=True)
class DastPrerequisiteCheck:
    """Repos that need discovery output before DAST tools can run."""

    missing_repos: list[Repository]


class DastPrerequisiteService:
    """Resolves DAST tool prerequisites without user interaction."""

    def check(
        self,
        tools: list[str],
        target_repos: list[Repository],
        has_url_findings_fn: Callable[[object], bool],
    ) -> DastPrerequisiteCheck | None:
        """Return repos needing discovery, or None if no action needed."""
        if not (DAST_TOOLS & set(tools)):
            return None
        if DISCOVERY_TOOLS & set(tools):
            return None

        missing = [
            r for r in target_repos if r.crawl_enabled and not has_url_findings_fn(r)
        ]
        if not missing:
            return None

        return DastPrerequisiteCheck(missing_repos=missing)

    def resolve_discovery_tools(self, missing_repos: list[Repository]) -> list[str]:
        """Katana always; noir only when at least one repo supports it."""
        to_prepend: list[str] = ["katana"]
        if any(noir_skip_reason(r) is None for r in missing_repos):
            to_prepend.append("noir")
        return to_prepend

    def prepend_prerequisites(
        self, discovery_tools: list[str], existing_tools: list[str]
    ) -> list[str]:
        """Return existing_tools with discovery_tools prepended."""
        existing = [t for t in existing_tools if t not in discovery_tools]
        return discovery_tools + existing

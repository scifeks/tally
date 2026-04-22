"""Scan orchestration: coordinate multi-tool scans across segments and repositories."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.ports.user_prompt import UserPromptPort
from application.tools.display import OrchestratorDisplay
from application.tools.executor import ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.registry import ToolRegistry
from application.tools.scan_types import (
    ExecutionResources,
    FullScan,
    RepoScan,
    SegmentScan,
    ToolOnAllReposScan,
    ToolOnRepoScan,
)
from domain.pipeline.events import EventBus
from domain.tools.scan_types import SEGMENT_ORDER, ScanSummary, ScanTypeConfig

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)

# Re-export constants so existing imports from this module continue to work.
__all__ = [
    "ScanSummary",
    "ScanOrchestrator",
    "SEGMENT_ORDER",
]


# ---------------------------------------------------------------------------
# ScanOrchestrator — thin shim
# ---------------------------------------------------------------------------


class ScanOrchestrator:
    """Coordinate multi-tool scans across segments and repositories.

    Args:
        project:        Active project name.
        tool_registry:  Registry of available tool wrappers.
        tool_executor:  Configured executor (carries base_path and project_name).
        event_bus:      EventBus for dispatching ToolCompleted events.
        prompt:         UserPromptPort adapter (REPL or API).
        run_id:         Optional run ID forwarded through events.
        factory:        Optional ToolWrapperFactory; defaults to a fresh instance.
        console:        Optional Rich console for display output.
    """

    def __init__(
        self,
        project: str,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        event_bus: EventBus,
        prompt: UserPromptPort,
        run_id: int | None = None,
        factory: ToolWrapperFactory | None = None,
        console: Console | None = None,
    ) -> None:
        self.project_name = project
        self.registry = tool_registry
        self.executor = tool_executor
        self._event_bus = event_bus
        self._prompt = prompt
        self._run_id = run_id
        self.display = OrchestratorDisplay(console=console)
        self._factory = factory or ToolWrapperFactory()

        from core.config.manager import ConfigManager

        self._config = ConfigManager(str(tool_executor.base_path))

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _make_config(self, remaining_peers: int = 0) -> ScanTypeConfig:
        """Build a ScanTypeConfig from current orchestrator state."""
        return ScanTypeConfig(
            project_name=self.project_name,
            base_path=str(self.executor.base_path),
            config_manager=self._config,
            run_id=self._run_id,
            prompt=self._prompt,
            remaining_peers=remaining_peers,
        )

    def _make_resources(self) -> ExecutionResources:
        """Build an ExecutionResources from current orchestrator state."""
        return ExecutionResources(
            executor=self.executor,
            registry=self.registry,
            factory=self._factory,
            event_bus=self._event_bus,
            display=self.display,
        )

    # ------------------------------------------------------------------
    # Public API — adapter shims
    # ------------------------------------------------------------------

    def run_full_scan(
        self,
        exclude_segments: list[str] | None = None,
        exclude_tools: set[str] | None = None,
    ) -> ScanSummary:
        return FullScan(exclude_segments or [], exclude_tools or set()).execute(
            self._make_config(), self._make_resources()
        )

    def run_segment(
        self,
        segment_name: str,
        remaining_peers: int = 0,
    ) -> ScanSummary:
        return SegmentScan(segment_name).execute(
            self._make_config(remaining_peers=remaining_peers),
            self._make_resources(),
        )

    def run_repo_scan(
        self,
        repo_name: str,
        exclude_dirs: list[str] | None = None,
        severity_filter: str | None = None,
        exclude_tools: set[str] | None = None,
    ) -> ScanSummary:
        return RepoScan(repo_name, exclude_tools or set()).execute(
            self._make_config(), self._make_resources()
        )

    def run_tool_on_all_repos(
        self,
        tool_name: str,
        remaining_peers: int = 0,
    ) -> ScanSummary:
        return ToolOnAllReposScan(tool_name).execute(
            self._make_config(remaining_peers=remaining_peers),
            self._make_resources(),
        )

    def run_tool_on_repo(
        self,
        tool_name: str,
        repo_name: str,
        remaining_peers: int = 0,
    ) -> ScanSummary:
        return ToolOnRepoScan(tool_name, repo_name).execute(
            self._make_config(remaining_peers=remaining_peers),
            self._make_resources(),
        )

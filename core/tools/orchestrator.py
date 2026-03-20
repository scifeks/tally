"""Scan orchestration: coordinate multi-tool scans across segments and repositories."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.pipeline.events import EventBus
from core.tools.display import OrchestratorDisplay
from core.tools.executor import ToolExecutor
from core.tools.factory import ToolWrapperFactory
from core.tools.registry import ToolRegistry
from core.tools.scan_types import (
    SEGMENT_ORDER,
    FullScan,
    RepoScan,
    ScanSummary,
    ScanTypeConfig,
    SegmentScan,
    ToolOnAllReposScan,
    ToolOnRepoScan,
)

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
        run_id: int | None = None,
        factory: ToolWrapperFactory | None = None,
        console: Console | None = None,
        auto_approve: bool = False,
    ) -> None:
        self.project_name = project
        self.registry = tool_registry
        self.executor = tool_executor
        self._event_bus = event_bus
        self._run_id = run_id
        self.display = OrchestratorDisplay(console=console)
        self._auto_approve: bool = auto_approve
        self._factory = factory or ToolWrapperFactory()

        from core.config.manager import ConfigManager

        self._config = ConfigManager(str(tool_executor.base_path))

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _make_config(self, auto_approve: bool = False) -> ScanTypeConfig:
        """Build a ScanTypeConfig from current orchestrator state."""
        return ScanTypeConfig(
            project_name=self.project_name,
            base_path=str(self.executor.base_path),
            executor=self.executor,
            registry=self.registry,
            config_manager=self._config,
            event_bus=self._event_bus,
            display=self.display,
            run_id=self._run_id,
            auto_approve=auto_approve or self._auto_approve,
            factory=self._factory,
        )

    # ------------------------------------------------------------------
    # Public API — adapter shims
    # ------------------------------------------------------------------

    def run_full_scan(
        self,
        auto_approve: bool = False,
        exclude_segments: list[str] | None = None,
    ) -> ScanSummary:
        return FullScan(exclude_segments or []).execute(self._make_config(auto_approve))

    def run_segment(
        self,
        segment_name: str,
        auto_approve: bool = False,
    ) -> ScanSummary:
        return SegmentScan(segment_name).execute(self._make_config(auto_approve))

    def run_repo_scan(
        self,
        repo_name: str,
        auto_approve: bool = False,
        exclude_dirs: list[str] | None = None,
        severity_filter: str | None = None,
    ) -> ScanSummary:
        return RepoScan(repo_name).execute(self._make_config(auto_approve))

    def run_tool_on_all_repos(
        self,
        tool_name: str,
        auto_approve: bool = False,
    ) -> ScanSummary:
        return ToolOnAllReposScan(tool_name).execute(self._make_config(auto_approve))

    def run_tool_on_repo(
        self,
        tool_name: str,
        repo_name: str,
        auto_approve: bool = False,
    ) -> ScanSummary:
        return ToolOnRepoScan(tool_name, repo_name).execute(
            self._make_config(auto_approve)
        )

"""ToolInterface ABC and supporting dataclasses for Phase 1 refactor.

These types are dormant in Phase 1 — wrappers implement them but the
orchestrator does not call them yet.  Phase 6 will cut the orchestrator over.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from core.config.manager import ConfigManager
    from core.config.schemas import Repository
    from core.tools.registry import ToolRegistry

from core.tools.base import ToolResult


@dataclass
class ExecutionPass:
    """A single invocation unit for a tool (one subprocess call)."""

    label_suffix: str
    kwargs: dict[str, Any]
    cwd: str | None = None


@dataclass
class ExecutionContext:
    """Everything a tool needs to build its execution passes."""

    project_name: str
    base_path: str
    repo: Repository | None  # None for network tools
    config_manager: ConfigManager
    registry: ToolRegistry
    is_docker: bool
    execution_mode: Literal["scan", "manual"] = "scan"
    # currently dead; TODO: implement when gate-level exclusion is required
    exclude_dirs: list[str] = field(default_factory=list)


class ToolInterface(ABC):
    """Polymorphic interface that all tool wrappers implement.

    Wrappers inherit from both ``ToolWrapper` and
    ``ToolInterface``.  Python MRO satisfies both ABCs; concrete classes
    implement each abstract member once.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def scan_segment(self) -> str:
        """Logical scan segment this tool belongs to (e.g. 'network', 'sast')."""
        ...

    @property
    @abstractmethod
    def findings_exit_ok(self) -> bool:
        """True if the tool exits non-zero when findings are present."""
        ...

    @property
    @abstractmethod
    def language_gates(self) -> list[str]:
        """Languages this tool applies to; empty list means language-agnostic."""
        ...

    @property
    @abstractmethod
    def requires_base_urls(self) -> bool:
        """True if the tool requires repo.base_urls to be configured."""
        ...

    @abstractmethod
    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass per subprocess invocation required."""
        ...

    @abstractmethod
    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        """Combine results from all passes into a single ToolResult."""
        ...

    @abstractmethod
    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        """Return the number of findings in parsed_data."""
        ...

    @property
    def display_fields(self) -> list[str]:
        """Optional ordered list of field names to show in result tables."""
        return []

"""ToolInterface ABC and supporting dataclasses for tool wrappers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from core.config.schemas import RepoService, Repository
    from domain.tools.execution_config import ToolExecutionConfig

from domain.tools.base import ToolResult


class RegistryLike(Protocol):
    """Pure-domain protocol satisfied by any registry that can resolve service paths.

    Defined here so that domain types carry no runtime dependency on
    application.tools.registry.ToolRegistry.
    """

    def get_service_path(self, tool_name: str, service, repo_path: str) -> str:
        """Return the filesystem path to use for the given tool and service."""
        ...


@dataclass
class ExecutionPass:
    """A single invocation unit for a tool (one subprocess call)."""

    label_suffix: str
    kwargs: dict[str, Any]
    cwd: str | None = None
    env: dict[str, str] | None = None


@dataclass
class ExecutionContext:
    """Everything a tool needs to build its execution passes."""

    project_name: str
    base_path: str
    repo: Repository | None  # None when not repo-scoped
    service: RepoService
    tool_config: ToolExecutionConfig
    registry: RegistryLike
    is_docker: bool
    execution_mode: Literal["scan", "manual"] = "scan"


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
        """Logical scan segment this tool belongs to (e.g. 'sast')."""
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

    @property
    @abstractmethod
    def always_run(self) -> bool:
        """True if this tool runs on every repo scan regardless of language gates."""
        ...

    @property
    @abstractmethod
    def candidate_commands(self) -> list[str]:
        """Binary names to try with shutil.which during setup auto-detection."""
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
    @abstractmethod
    def skip(self) -> bool:
        """True if this tool produces no triage-able findings."""
        ...

    @property
    @abstractmethod
    def should_visualize(self) -> bool:
        """True if this tool's findings should appear in visualization (web UI).

        Tools that produce metadata rather than triage-able findings (e.g., noir)
        set this to False to exclude them from the findings browser table.
        """
        ...

    @property
    def is_discovery_tool(self) -> bool:
        """True if this tool discovers endpoints/attack-surface (not vulnerabilities).

        Discovery tools run before scanner tools within the same segment.
        Override to ``True`` on endpoint-discovery wrappers (Noir, Katana).
        """
        return False

    @property
    def timeout(self) -> int | None:
        """Per-tool subprocess timeout in seconds.

        Return ``None`` to defer to the executor's ``DEFAULT_TIMEOUT``.
        Override in subclasses for tools that routinely need more (or less) time.
        """
        return None

    @property
    def display_fields(self) -> list[str]:
        """Optional ordered list of field names to show in result tables."""
        return []

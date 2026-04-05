from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: str
    parsed_data: dict[str, Any] | None
    output_files: dict[str, Path]
    timestamp: str
    duration_seconds: float
    finding_count: int = 0

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()


class ToolWrapper(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def command(self) -> str: ...

    @property
    @abstractmethod
    def category(self) -> str: ...

    @property
    @abstractmethod
    def scope(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def supported_languages(self) -> list[str] | None:
        return None

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if the tool binary is present on PATH."""

    @abstractmethod
    def build_command(self, **kwargs) -> list[str]:
        """Return the full argv list for this tool invocation."""

    @abstractmethod
    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse raw tool output into a structured dict."""

    @abstractmethod
    def get_version(self) -> str | None: ...

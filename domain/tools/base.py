import shutil
import subprocess
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

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()


def get_tool_version(command: str) -> str | None:
    """Run `<command> --version` and return the first line, or None."""
    binary = shutil.which(command)
    if binary is None:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr).strip()
        return output.splitlines()[0] if output else None
    except Exception:
        return None


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

    def get_version(self) -> str | None:
        """Run `<command> --version` and return the first line, or None."""
        binary = shutil.which(self.command)
        if binary is None:
            return None
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (result.stdout or result.stderr).strip()
            return output.splitlines()[0] if output else None
        except Exception:
            return None

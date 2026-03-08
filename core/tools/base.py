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


class DockerToolWrapper(ToolWrapper, ABC):
    """Base class for tools executed via ``docker exec`` inside a container.

    Subclasses implement ``name``, ``category``, ``scope``, ``description``,
    ``build_command``, and ``parse_output``.  ``container_name`` and
    ``tool_path`` are resolved from the ``CommandEntry`` passed at
    instantiation by the registry.
    """

    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    # ------------------------------------------------------------------
    # Concrete properties supplied by config
    # ------------------------------------------------------------------

    @property
    def container_name(self) -> str:
        return self._container_name

    @property
    def tool_path(self) -> str:
        return self._tool_path

    @property
    def command(self) -> str:
        # The host-side executable is always "docker"
        return "docker"

    # ------------------------------------------------------------------
    # Availability — presence in commands.json means the user configured it
    # ------------------------------------------------------------------

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    # ------------------------------------------------------------------
    # Protected helper
    # ------------------------------------------------------------------

    def _build_docker_exec(
        self,
        tool_args: list[str],
        workdir: str | None = None,
    ) -> list[str]:
        """Build a ``docker exec`` argv list.

        Args:
            tool_args: Arguments passed to the tool binary inside the container.
            workdir:   If set, adds ``-w <workdir>`` before the container name.

        Returns:
            Full argv list starting with ``["docker", "exec", ...]``.
        """
        cmd = ["docker", "exec"]
        if workdir:
            cmd.extend(["-w", workdir])
        cmd.extend([self._container_name, self._tool_path])
        cmd.extend(tool_args)
        return cmd

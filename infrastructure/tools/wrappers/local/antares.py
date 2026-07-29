"""Local Antares tool wrapper."""

import shutil
from typing import Any

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.antares import BaseAntaresTool


class AntaresLocalTool(BaseAntaresTool):
    """Local Antares CWE scanner wrapper."""

    def __init__(self, config: Any = None) -> None:
        super().__init__()

    @property
    def command(self) -> str:
        return "antares"

    def check_available(self) -> bool:
        return shutil.which("antares") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs: Any) -> list[str]:
        mode = kwargs.get("mode", "sweep")
        return ["antares", "tool", mode, "--stdin"]

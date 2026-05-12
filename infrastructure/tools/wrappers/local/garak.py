"""Garak local wrapper."""

import shutil
from pathlib import Path

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.garak import (
    BaseGarakTool,
)


class GarakLocalTool(BaseGarakTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "garak"

    def check_available(self) -> bool:
        return shutil.which(self.command) is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs: object) -> list[str]:
        config_path = str(kwargs.get("config_path", ""))
        if not config_path:
            raise ValueError("config_path is required for garak")

        if not Path(config_path).exists():
            raise ValueError(f"Config file not found: {config_path!r}")
        return [self.command, "--config", config_path, "--skip_unknown"]

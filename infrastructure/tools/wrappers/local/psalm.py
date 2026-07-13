import shutil
from pathlib import Path

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.psalm import BasePsalmTool


class PsalmLocalTool(BasePsalmTool):
    def __init__(self, config=None) -> None:
        self._binary: str = (
            config.path if config is not None and config.path else "psalm"
        )

    @property
    def command(self) -> str:
        return self._binary

    def check_available(self) -> bool:
        return Path(self._binary).exists() or shutil.which(self._binary) is not None

    def get_version(self) -> str | None:
        return get_tool_version(self._binary)

    def build_command(self, **kwargs) -> list[str]:
        repo_path: str | None = kwargs.get("repo_path")
        config_path: str | None = kwargs.get("config_path")
        sarif_path: str | None = kwargs.get("sarif_path")

        if not repo_path:
            raise ValueError("repo_path is required for psalm")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        if not config_path:
            raise ValueError("config_path is required for psalm")
        if not sarif_path:
            raise ValueError("sarif_path is required for psalm")

        return [
            self._binary,
            f"--config={config_path}",
            f"--report={sarif_path}",
            "--no-cache",
            "--no-progress",
        ]

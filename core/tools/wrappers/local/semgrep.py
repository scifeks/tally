import shutil
from pathlib import Path

from ...base import get_tool_version
from ..base.semgrep import BaseSemgrepTool


class SemgrepLocalTool(BaseSemgrepTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "semgrep"

    def check_available(self) -> bool:
        return shutil.which("semgrep") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        """Build the semgrep argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            config (str): Semgrep ruleset/config (default: "auto").
            severity (List[str]): Only report findings at these severities.
            exclude (List[str]): Glob patterns for paths to exclude.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for semgrep")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        config: str = kwargs.get("config", "auto")
        severity: list[str] | None = kwargs.get("severity")
        exclude: list[str] | None = kwargs.get("exclude")

        # --json sends findings as JSON to stdout; executor captures and saves it
        cmd = ["semgrep", "scan", "--config", config, "--json", repo_path]

        if severity:
            for sev in severity:
                cmd.extend(["--severity", sev.upper()])

        if exclude:
            for pattern in exclude:
                cmd.extend(["--exclude", pattern])

        return cmd

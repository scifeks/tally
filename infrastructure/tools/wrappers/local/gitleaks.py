import tempfile
from pathlib import Path
from typing import Any

from domain.tools.base import get_tool_version
from infrastructure.tools.parsers.gitleaks_parser import (
    parse_gitleaks_json,
    parse_gitleaks_json_string,
)
from infrastructure.tools.wrappers.base.gitleaks import BaseGitleaksTool


class GitleaksLocalTool(BaseGitleaksTool):
    def __init__(self, config=None) -> None:
        self._last_report_path: Path | None = None

    @property
    def command(self) -> str:
        return "gitleaks"

    def check_available(self) -> bool:
        import shutil

        return shutil.which("gitleaks") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        """Build the gitleaks argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            scan_type (str): 'dir' for working-tree scan or 'git' for full
                             history scan (default: 'dir').
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for gitleaks")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        scan_type: str = kwargs.get("scan_type", "dir")
        if scan_type not in ("dir", "git"):
            raise ValueError(f"scan_type must be 'dir' or 'git', got {scan_type!r}")

        tmp = tempfile.mktemp(suffix=".json", prefix=f"gitleaks_{scan_type}_")
        self._last_report_path = Path(tmp)

        gitleaks_ignore_path: str | None = kwargs.get("gitleaks_ignore_path")

        cmd = [
            "gitleaks",
            scan_type,
            repo_path,
            "--report-format",
            "json",
            "--report-path",
            tmp,
            "--exit-code",
            "0",
        ]
        if gitleaks_ignore_path:
            cmd.extend(["--gitleaks-ignore-path", gitleaks_ignore_path])
        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse gitleaks JSON output into structured data.

        Prefers the report file written via --report-path; falls back to the
        saved stdout file, then parses the raw output string.
        """
        if self._last_report_path is not None and self._last_report_path.exists():
            return parse_gitleaks_json(self._last_report_path)
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_gitleaks_json(json_path)
        return parse_gitleaks_json_string(output)

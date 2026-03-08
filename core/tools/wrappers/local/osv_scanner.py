"""OSV-Scanner wrapper for dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path
from typing import Any

from ...base import ToolWrapper
from ...parsers.osv_parser import parse_osv_json, parse_osv_json_string


class OSVScannerWrapper(ToolWrapper):
    def __init__(self, config=None) -> None:
        pass

    @property
    def name(self) -> str:
        return "osv-scanner"

    @property
    def command(self) -> str:
        return "osv-scanner"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Dependency vulnerability scanner using OSV database"

    @property
    def supported_languages(self) -> list[str] | None:
        return None

    def check_available(self) -> bool:
        return shutil.which("osv-scanner") is not None

    def build_command(self, **kwargs) -> list[str]:
        """Build the osv-scanner argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            recursive (bool): Recursively scan subdirectories (default: True).
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for osv-scanner")
        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        recursive: bool = kwargs.get("recursive", True)

        # --format json sends findings as JSON to stdout; executor captures it
        cmd = ["osv-scanner", "--format", "json"]
        if recursive:
            cmd.append("--recursive")
        cmd.append(repo_path)
        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse osv-scanner JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_osv_json(json_path)
        return parse_osv_json_string(output)

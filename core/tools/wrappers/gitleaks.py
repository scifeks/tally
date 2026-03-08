import shutil
from pathlib import Path
from typing import Any

from ..base import ToolWrapper
from ..parsers.gitleaks_parser import parse_gitleaks_json, parse_gitleaks_json_string


class GitleaksWrapper(ToolWrapper):
    @property
    def name(self) -> str:
        return "gitleaks"

    @property
    def command(self) -> str:
        return "gitleaks"

    @property
    def category(self) -> str:
        return "secrets"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Secrets detection tool for git repositories and files"

    @property
    def supported_languages(self) -> list[str] | None:
        return None

    def check_available(self) -> bool:
        return shutil.which("gitleaks") is not None

    def build_command(self, **kwargs) -> list[str]:
        """Build the gitleaks argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            scan_uncommitted (bool): Scan uncommitted changes in a git repo
                (default: False). When True, omits --no-git and adds --uncommitted.
            verbose (bool): Enable verbose output (default: False).
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for gitleaks")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        scan_uncommitted: bool = bool(kwargs.get("scan_uncommitted", False))
        verbose: bool = bool(kwargs.get("verbose", False))

        cmd = [
            "gitleaks",
            "detect",
            "--source",
            repo_path,
            "--report-format",
            "json",
        ]

        if scan_uncommitted:
            cmd.append("--uncommitted")
        else:
            # Scan working tree files without requiring a git repository
            cmd.append("--no-git")

        if verbose:
            cmd.append("--verbose")

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse gitleaks JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_gitleaks_json(json_path)
        return parse_gitleaks_json_string(output)

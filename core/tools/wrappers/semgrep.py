import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ToolWrapper
from ..parsers.semgrep_parser import parse_semgrep_json, parse_semgrep_json_string


class SemgrepWrapper(ToolWrapper):
    @property
    def name(self) -> str:
        return "semgrep"

    @property
    def command(self) -> str:
        return "semgrep"

    @property
    def category(self) -> str:
        return "sast"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Static analysis tool for finding bugs and security issues"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return None

    def check_available(self) -> bool:
        return shutil.which("semgrep") is not None

    def build_command(self, **kwargs) -> List[str]:
        """Build the semgrep argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
            config (str): Semgrep ruleset/config (default: "auto").
            severity (List[str]): Only report findings at these severities.
            exclude (List[str]): Glob patterns for paths to exclude.
        """
        repo_path: Optional[str] = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for semgrep")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        config: str = kwargs.get("config", "auto")
        severity: Optional[List[str]] = kwargs.get("severity")
        exclude: Optional[List[str]] = kwargs.get("exclude")

        # --json sends findings as JSON to stdout; executor captures and saves it
        cmd = ["semgrep", "scan", "--config", config, "--json", repo_path]

        if severity:
            for sev in severity:
                cmd.extend(["--severity", sev.upper()])

        if exclude:
            for pattern in exclude:
                cmd.extend(["--exclude", pattern])

        return cmd

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        """Parse semgrep JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_semgrep_json(json_path)
        return parse_semgrep_json_string(output)

"""pip-audit wrapper for Python dependency vulnerability scanning (SCA)."""

import shutil
from pathlib import Path
from typing import Any

from ..base import ToolWrapper
from ..parsers.pip_audit_parser import parse_pip_audit_json, parse_pip_audit_json_string


class PipAuditWrapper(ToolWrapper):
    @property
    def name(self) -> str:
        return "pip-audit"

    @property
    def command(self) -> str:
        return "pip-audit"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Python dependency vulnerability scanner using PyPI advisory database"

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python"]

    def check_available(self) -> bool:
        return shutil.which("pip-audit") is not None

    def build_command(self, **kwargs) -> list[str]:
        """Build the pip-audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).

        The command targets requirements.txt if present, otherwise falls back
        to --path for projects using pyproject.toml / setup.cfg / setup.py.
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for pip-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        cmd = ["pip-audit", "--format", "json"]

        req_file = repo / "requirements.txt"
        if req_file.exists():
            cmd.extend(["-r", str(req_file)])
        elif (
            (repo / "pyproject.toml").exists()
            or (repo / "setup.cfg").exists()
            or (repo / "setup.py").exists()
        ):
            cmd.extend(["--path", str(repo)])
        else:
            raise ValueError(
                "No Python manifest (requirements.txt, pyproject.toml, setup.py)"
                f" found in {repo_path!r}"
            )

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse pip-audit JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_pip_audit_json(json_path)
        return parse_pip_audit_json_string(output)

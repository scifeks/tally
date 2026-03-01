"""npm-audit wrapper for Node.js dependency vulnerability scanning (SCA)."""
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ToolWrapper
from ..parsers.npm_audit_parser import parse_npm_audit_json, parse_npm_audit_json_string


class NpmAuditWrapper(ToolWrapper):
    @property
    def name(self) -> str:
        return "npm-audit"

    @property
    def command(self) -> str:
        return "npm"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Node.js dependency vulnerability scanner using npm advisory database"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return ["javascript", "typescript", "node"]

    def check_available(self) -> bool:
        return shutil.which("npm") is not None

    def build_command(self, **kwargs) -> List[str]:
        """Build the npm audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
                             Must contain a package.json file.

        Note:
            npm audit must run in the directory containing package.json.
            The executor must be called with ``cwd=repo_path`` so the
            subprocess runs inside the repository directory.
        """
        repo_path: Optional[str] = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for npm-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        if not (repo / "package.json").exists():
            raise ValueError(f"No package.json found in {repo_path!r}")

        return ["npm", "audit", "--json"]

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        """Parse npm audit JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_npm_audit_json(json_path)
        return parse_npm_audit_json_string(output)

"""composer-audit wrapper for PHP dependency vulnerability scanning (SCA)."""
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ToolWrapper
from ..parsers.composer_audit_parser import (
    parse_composer_audit_json,
    parse_composer_audit_json_string,
)


class ComposerAuditWrapper(ToolWrapper):
    @property
    def name(self) -> str:
        return "composer-audit"

    @property
    def command(self) -> str:
        return "composer"

    @property
    def category(self) -> str:
        return "sca"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "PHP dependency vulnerability scanner using Packagist security advisories"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return ["php"]

    def check_available(self) -> bool:
        return shutil.which("composer") is not None

    def build_command(self, **kwargs) -> List[str]:
        """Build the composer audit argv list.

        Keyword Args:
            repo_path (str): Path to the repository to scan (required).
                             Must contain a composer.json file.

        Note:
            composer audit must run in the directory containing composer.json.
            The executor must be called with ``cwd=repo_path`` so the
            subprocess runs inside the repository directory.
        """
        repo_path: Optional[str] = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for composer-audit")

        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        if not (repo / "composer.json").exists():
            raise ValueError(f"No composer.json found in {repo_path!r}")

        return ["composer", "audit", "--format=json"]

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        """Parse composer audit JSON output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_composer_audit_json(json_path)
        return parse_composer_audit_json_string(output)

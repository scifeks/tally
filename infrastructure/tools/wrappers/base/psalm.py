"""Shared base class for psalm local and docker wrappers."""

import json
import logging
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from core.config.schemas import RepoService, Repository
from domain.tools.base import ToolResult
from domain.tools.interface import (
    ExecutionContext,
    ExecutionPass,
    ToolInterface,
)
from infrastructure.tools.parsers.psalm import (
    parse_psalm_sarif,
    parse_psalm_sarif_string,
)

_log = logging.getLogger(__name__)


class BasePsalmTool(ToolInterface):
    _candidate_commands: list[str] = ["psalm"]
    _command_entry_type: str = "repo"

    def __init__(self) -> None:
        self._temp_dir: str | None = None
        self._sarif_path: Path | None = None

    @property
    def name(self) -> str:
        return "psalm"

    @property
    def category(self) -> str:
        return "sast"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "PHP taint analysis; traces data flow from user input to dangerous sinks"

    @property
    def scan_segment(self) -> str:
        return "sast"

    @property
    def skip(self) -> bool:
        return False

    @property
    def should_visualize(self) -> bool:
        return True

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return ["php"]

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def always_run(self) -> bool:
        return False

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def parse_output(
        self,
        output: str,
        _files: dict[str, Path],
    ) -> dict[str, Any]:
        """Parse psalm SARIF output into structured data.

        Prefers the saved SARIF file; falls back to output string.
        """
        try:
            if (
                self._sarif_path is not None
                and self._sarif_path.exists()
                and self._sarif_path.stat().st_size > 0
            ):
                return parse_psalm_sarif(self._sarif_path)
            return parse_psalm_sarif_string(output)
        finally:
            if self._temp_dir:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                self._temp_dir = None
                self._sarif_path = None

    def build_execution_passes(
        self,
        context: ExecutionContext,
    ) -> list[ExecutionPass]:
        assert context.repo is not None
        assert context.service is not None

        repo_path = context.registry.get_service_path(
            self.name,
            context.service,
            context.repo.path,
        )

        self._temp_dir = tempfile.mkdtemp(prefix="tally-psalm-")
        config_path = self._generate_psalm_config(
            self._temp_dir,
            context.repo,
            context.service,
        )
        self._sarif_path = Path(self._temp_dir) / "results.sarif"

        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={
                    "repo_path": repo_path,
                    "config_path": str(config_path),
                    "sarif_path": str(self._sarif_path),
                },
            ),
        ]

    def merge_pass_results(
        self,
        pass_results: list[ToolResult],
    ) -> ToolResult:
        return pass_results[0]

    def count_findings(
        self,
        parsed_data: dict[str, Any],
    ) -> int:
        summary = parsed_data.get("summary", {})
        if "total_findings" in summary:
            return summary["total_findings"]
        return len(parsed_data.get("findings", []))

    def _generate_psalm_config(
        self,
        temp_dir: str,
        repo: Repository,
        _service: RepoService,
    ) -> Path:
        """Generate psalm.xml config file."""
        source_dirs = self._find_source_dirs(repo.path)
        stubs_paths = self._resolve_stubs(repo.psalm_stubs)
        xml_str = self._build_psalm_xml(source_dirs, stubs_paths, repo.path)

        config_path = Path(temp_dir) / "psalm.xml"
        config_path.write_text(xml_str)
        return config_path

    def _find_source_dirs(self, repo_path: str) -> list[str]:
        """Find source directories from composer.json or psalm.xml."""
        repo_p = Path(repo_path)

        composer_json = repo_p / "composer.json"
        if composer_json.exists():
            try:
                data = json.loads(composer_json.read_text())
                autoload = data.get("autoload", {})
                psr4 = autoload.get("psr-4", {})
                if psr4:
                    dirs = [v.rstrip("/") for v in psr4.values()]
                    return dirs
            except Exception as exc:
                _log.warning(
                    "Failed to parse composer.json: %s",
                    exc,
                )

        psalm_xml = repo_p / "psalm.xml"
        if psalm_xml.exists():
            try:
                tree = ET.parse(psalm_xml)
                root = tree.getroot()
                dirs = self._extract_directories_from_psalm_xml(root)
                if dirs:
                    return dirs
            except Exception as exc:
                _log.warning(
                    "Failed to parse psalm.xml: %s",
                    exc,
                )

        return ["."]

    def _extract_directories_from_psalm_xml(self, root: ET.Element) -> list[str]:
        """Extract directory names from parsed psalm.xml root element."""
        ns = "https://getpsalm.org/schema/config"

        project_files = root.find(f"{{{ns}}}projectFiles")
        if project_files is None:
            project_files = root.find(".//projectFiles")

        if project_files is not None:
            dirs = []
            for directory in project_files.findall(f"{{{ns}}}directory"):
                dir_name = directory.get("name")
                if dir_name:
                    dirs.append(dir_name)
            if not dirs:
                for directory in project_files.findall("directory"):
                    dir_name = directory.get("name")
                    if dir_name:
                        dirs.append(dir_name)
            return dirs

        return []

    def _resolve_stubs(self, psalm_stubs: list[str]) -> list[str]:
        """Resolve stub file names to absolute paths."""
        stub_names = list(dict.fromkeys(["php_builtins"] + psalm_stubs))
        stubs_dir = Path(__file__).resolve().parent.parent.parent / "stubs" / "psalm"
        resolved = []

        for name in stub_names:
            stub_file = stubs_dir / f"{name}.phpstub"
            if stub_file.exists():
                resolved.append(str(stub_file.absolute()))
            else:
                _log.warning(
                    "Psalm stub file not found: %s",
                    stub_file,
                )

        return resolved

    def _build_psalm_xml(
        self,
        source_dirs: list[str],
        stubs_paths: list[str],
        repo_path: str,
    ) -> str:
        """Generate psalm.xml configuration as XML string."""
        lines = [
            '<?xml version="1.0"?>',
            "<psalm",
            '    errorLevel="1"',
            '    runTaintAnalysis="true"',
            '    xmlns="https://getpsalm.org/schema/config"',
            ">",
            "    <projectFiles>",
        ]

        for dir_name in source_dirs:
            lines.append(f'        <directory name="{dir_name}" />')

        lines.append("    </projectFiles>")

        if stubs_paths:
            lines.append("    <stubs>")
            for stub_path in stubs_paths:
                lines.append(f'        <file name="{stub_path}" />')
            lines.append("    </stubs>")

        autoloader_path = Path(repo_path) / "vendor" / "autoload.php"
        if autoloader_path.exists():
            abs_path = str(autoloader_path.absolute())
            lines.append(f'    <autoloader filename="{abs_path}" />')

        lines.append("</psalm>")
        return "\n".join(lines)

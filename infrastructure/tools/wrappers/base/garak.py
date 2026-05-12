"""Shared base class for garak wrappers."""

from pathlib import Path
from typing import Any

import yaml

from core.project_paths import ProjectPaths
from domain.tools.base import ToolResult
from domain.tools.interface import (
    ExecutionContext,
    ExecutionPass,
    ToolInterface,
)
from infrastructure.tools.parsers.garak import (
    parse_garak_report,
)


def _remap_deprecated_keys(cfg: dict) -> None:
    plugins = cfg.get("plugins", {})
    if "model_type" in plugins:
        plugins["target_type"] = plugins.pop("model_type")
    if "model_name" in plugins:
        plugins["target_name"] = plugins.pop("model_name")


def _build_run_config(user_config: Path, output_dir: Path, report_prefix: str) -> Path:
    with open(user_config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    _remap_deprecated_keys(cfg)
    reporting = cfg.setdefault("reporting", {})
    reporting["report_dir"] = str(output_dir.resolve())
    reporting["report_prefix"] = report_prefix

    run_config = output_dir / f"{report_prefix}_config.yaml"
    with open(run_config, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)
    return run_config


_DEFAULT_TIMEOUT = 3600


class BaseGarakTool(ToolInterface):
    _candidate_commands: list[str] = ["garak"]
    _command_entry_type: str = "repo"
    _output_dir: Path = Path()
    _report_prefix: str = ""
    _timeout: int = _DEFAULT_TIMEOUT

    @property
    def name(self) -> str:
        return "garak"

    @property
    def category(self) -> str:
        return "llm"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "LLM vulnerability scanner"

    @property
    def scan_segment(self) -> str:
        return "llm"

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
        return []

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
        return None

    @property
    def timeout(self) -> int | None:
        return self._timeout

    def parse_output(
        self,
        output: str,
        files: dict[str, Path],
    ) -> dict[str, Any]:
        report = self._output_dir / f"{self._report_prefix}.report.jsonl"
        if report.exists():
            return parse_garak_report(report)
        return {
            "findings": [],
            "summary": {"total_findings": 0},
        }

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        paths = ProjectPaths.from_canonical(context.base_path, context.project_name)

        if not (context.repo and context.repo.id is not None):
            return []
        user_config = paths.garak_config(context.repo.id)
        if not user_config.exists():
            return []

        self._output_dir = paths.tool_output_dir("garak")
        self._output_dir.mkdir(parents=True, exist_ok=True)

        repo_name = context.repo.name.replace(" ", "_").lower()
        self._report_prefix = f"garak_{repo_name}"

        with open(user_config, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        self._timeout = user_cfg.get("tally", {}).get("timeout", _DEFAULT_TIMEOUT)

        run_config = _build_run_config(
            user_config, self._output_dir, self._report_prefix
        )

        return [
            ExecutionPass(
                label_suffix="llm-scan",
                kwargs={"config_path": str(run_config)},
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get(
            "total_findings",
            len(parsed_data.get("findings", [])),
        )

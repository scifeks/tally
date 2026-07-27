"""Base class for Antares CWE localization scanner wrapper."""

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import (
    ExecutionContext,
    ExecutionPass,
    ToolInterface,
)
from infrastructure.llm.completions_shim import CompletionsShim
from infrastructure.tools.antares_trace import locate_trace_files
from infrastructure.tools.parsers.antares import (
    _parse_antares_data,
    parse_antares_json_string,
)

_log = logging.getLogger(__name__)


class BaseAntaresTool(ToolInterface):
    """Base wrapper for Antares CWE localization scanner."""

    def __init__(self) -> None:
        self._shim: CompletionsShim | None = None
        self._antares_data_dir: Path | None = None

    @property
    def name(self) -> str:
        return "antares"

    @property
    def scan_segment(self) -> str:
        return "sast"

    @property
    def findings_exit_ok(self) -> bool:
        return False

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def always_run(self) -> bool:
        return True

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def candidate_commands(self) -> list[str]:
        return ["antares"]

    @property
    def should_visualize(self) -> bool:
        return True

    @property
    def skip(self) -> bool:
        return False

    @property
    def timeout(self) -> int:
        return 7200

    def build_execution_passes(
        self,
        context: ExecutionContext,
    ) -> list[ExecutionPass]:
        """Build execution pass with stdin JSON payload and Antares env vars.

        If Antares is configured with Ollama provider, starts a completions
        shim that translates OpenAI API calls to Ollama generate calls.
        """
        assert context.repo is not None
        assert context.service is not None

        repo_path = context.registry.get_service_path(
            self.name,
            context.service,
            context.repo.path,
        )

        payload: dict[str, Any] = {"target": repo_path}

        from core.config.manager import ConfigManager
        from infrastructure.llm.antares_config_resolver import (
            resolve_antares_config,
        )

        config_mgr = ConfigManager(context.base_path)
        resolved = resolve_antares_config(config_mgr.global_config)

        endpoint_url = resolved.endpoint_url
        if resolved.needs_shim:
            assert resolved.ollama_base_url is not None, (
                "ollama_base_url must be set when needs_shim is True"
            )
            self._shim = CompletionsShim(resolved.ollama_base_url, resolved.model)
            endpoint_url = self._shim.start()

        self._antares_data_dir = Path(tempfile.mkdtemp(prefix="antares_"))

        env_vars: dict[str, str] = {
            "ANTARES_ENDPOINT": endpoint_url,
            "ANTARES_MODEL": resolved.model,
            "ANTARES_REMOTE_TIMEOUT_SECONDS": str(resolved.timeout_seconds),
            "ANTARES_DATA_DIR": str(self._antares_data_dir),
        }

        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={},
                stdin_data=json.dumps(payload),
                env=env_vars,
            ),
        ]

    def merge_pass_results(
        self,
        pass_results: list[ToolResult],
    ) -> ToolResult:
        """Return the first result; stop the shim and clean up."""
        try:
            return pass_results[0]
        finally:
            if self._shim is not None:
                self._shim.stop()
                self._shim = None
            if self._antares_data_dir is not None:
                try:
                    shutil.rmtree(self._antares_data_dir)
                except OSError:
                    pass

    def count_findings(
        self,
        parsed_data: dict[str, Any],
    ) -> int:
        """Count findings from parsed Antares output."""
        summary = parsed_data.get("summary", {})
        if "total_findings" in summary:
            return summary["total_findings"]
        return len(parsed_data.get("findings", []))

    def parse_output(
        self,
        output: str,
        files: dict[str, Path],
    ) -> dict[str, Any]:
        """Parse Antares JSON output and load investigation traces."""
        json_path = files.get("stdout")
        parsed_data = None
        if json_path is not None and json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self._log_scan_warnings(data)
                    parsed_data = _parse_antares_data(data)
            except (OSError, json.JSONDecodeError) as exc:
                _log.exception("Failed to parse stdout file: %s", json_path)
                return {"error": f"JSON parse error: {exc}"}
        else:
            try:
                data = json.loads(output)
                self._log_scan_warnings(data)
                parsed_data = _parse_antares_data(data)
            except json.JSONDecodeError:
                return parse_antares_json_string(output)

        if parsed_data is None:
            return {}

        if self._antares_data_dir is not None:
            trace_map = locate_trace_files(self._antares_data_dir)
            parsed_data["trace_map"] = trace_map

        return parsed_data

    def _log_scan_warnings(self, data: dict[str, Any]) -> None:
        """Log warnings for degraded scan results."""
        summary = data.get("summary", {})

        failed_workers = summary.get("failed_workers", 0)
        if failed_workers > 0:
            _log.warning(
                "Antares scan had %d failed worker(s)",
                failed_workers,
            )

        incomplete_reason = summary.get("incomplete_reason")
        if incomplete_reason is not None:
            _log.warning(
                "Antares scan did not complete: %s",
                incomplete_reason,
            )

        per_cwe_results = data.get("per_cwe_results", [])
        for cwe_result in per_cwe_results:
            error_msg = cwe_result.get("error_message")
            if error_msg is not None:
                cwe_id = cwe_result.get("cwe_id", "unknown")
                _log.warning(
                    "Antares CWE %s failed: %s",
                    cwe_id,
                    error_msg,
                )

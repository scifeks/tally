"""Base class for Antares CWE localization scanner wrapper."""

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from core.config.schemas import build_excluded_dirs
from domain.tools.base import ToolResult
from domain.tools.interface import (
    ExecutionContext,
    ExecutionPass,
    ToolInterface,
)
from infrastructure.llm.completions_shim import CompletionsShim
from infrastructure.tools.antares_trace import (
    build_trace_detail,
    build_trace_summary,
    locate_trace_files,
    parse_trace_file,
)
from infrastructure.tools.parsers.antares import (
    parse_antares_data,
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

    @property
    def category(self) -> str:
        return "sast"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "CWE vulnerability localization scanner using LLM agents"

    def build_execution_passes(
        self,
        context: ExecutionContext,
    ) -> list[ExecutionPass]:
        """Build execution pass with stdin JSON payload and Antares env vars.

        If Antares is configured with Ollama provider, starts a completions
        shim that translates OpenAI API calls to Ollama generate calls.
        """
        if context.repo is None or context.service is None:
            raise ValueError("repo and service are required")

        repo_path = context.registry.get_service_path(
            self.name,
            context.service,
            context.repo.path,
        )

        excluded = build_excluded_dirs(context.service)

        resolved = context.tool_config.antares_config
        if resolved is None:
            raise ValueError("antares_inference not configured")

        endpoint_url = resolved.endpoint_url
        if resolved.needs_shim:
            if resolved.ollama_base_url is None:
                raise ValueError("ollama_base_url must be set when needs_shim is True")
            self._shim = CompletionsShim(
                resolved.ollama_base_url,
                resolved.model,
                resolved.timeout_seconds,
            )
            endpoint_url = self._shim.start()

        try:
            self._antares_data_dir = Path(tempfile.mkdtemp(prefix="antares_"))

            payload: dict[str, Any] = {
                "target": repo_path,
                "model": resolved.model,
                "endpoint": endpoint_url,
            }
            if resolved.max_cwes is not None:
                payload["max_cwes"] = resolved.max_cwes
            if resolved.workers is not None:
                payload["workers"] = resolved.workers

            env_vars: dict[str, str] = {
                "ANTARES_ENDPOINT": endpoint_url,
                "ANTARES_MODEL": resolved.model,
                "ANTARES_REMOTE_TIMEOUT_SECONDS": str(resolved.timeout_seconds),
                "ANTARES_DATA_DIR": str(self._antares_data_dir),
            }
            if excluded:
                # Antares uses case-sensitive fnmatchcase; include
                # common case variants so "tests" matches "Tests".
                variants: set[str] = set()
                for d in excluded:
                    variants.update((d, d.lower(), d.title()))
                env_vars["ANTARES_IGNORE_PATHS"] = json.dumps(sorted(variants))

            return [
                ExecutionPass(
                    label_suffix=context.repo.name,
                    kwargs={},
                    stdin_data=json.dumps(payload),
                    env=env_vars,
                ),
            ]
        except Exception:
            if self._shim is not None:
                self._shim.stop()
                self._shim = None
            raise

    def merge_pass_results(
        self,
        pass_results: list[ToolResult],
    ) -> ToolResult:
        """Return the first result; stop the shim and clean up.

        Antares exits 2 on partial worker failures, which the executor
        marks as success=False. Override to success=True when parsed
        output contains valid findings so the ingest pipeline runs.
        """
        try:
            result = pass_results[0]
            if (
                not result.success
                and result.parsed_data
                and result.parsed_data.get("findings")
            ):
                result = ToolResult(
                    tool_name=result.tool_name,
                    success=True,
                    output=result.output,
                    parsed_data=result.parsed_data,
                    output_files=result.output_files,
                    timestamp=result.timestamp,
                    duration_seconds=result.duration_seconds,
                    finding_count=result.finding_count,
                    repo=result.repo,
                )
            return result
        finally:
            if self._shim is not None:
                self._shim.stop()
                self._shim = None
            if self._antares_data_dir is not None:
                try:
                    shutil.rmtree(self._antares_data_dir)
                except OSError:
                    _log.debug(
                        "Failed to remove temp dir: %s",
                        self._antares_data_dir,
                    )

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
        data = None
        if json_path is not None and json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self._log_scan_warnings(data)
                    parsed_data = parse_antares_data(data)
            except (OSError, json.JSONDecodeError) as exc:
                _log.exception("Failed to parse stdout file: %s", json_path)
                return {"error": f"JSON parse error: {exc}"}
        else:
            try:
                data = json.loads(output)
                self._log_scan_warnings(data)
                parsed_data = parse_antares_data(data)
            except json.JSONDecodeError:
                return parse_antares_json_string(output)

        if parsed_data is None:
            return {}

        if data is not None:
            raw_warnings = data.get("warnings", [])
            if raw_warnings:
                parsed_data["scan_warnings"] = raw_warnings

        if self._antares_data_dir is not None:
            trace_map = locate_trace_files(self._antares_data_dir)
            trace_data: dict[str, dict[str, Any]] = {}
            for cwe_id, trace_path in trace_map.items():
                events = parse_trace_file(trace_path)
                trace_data[cwe_id] = {
                    "summary": build_trace_summary(events),
                    "detail": build_trace_detail(events),
                }
            if trace_data:
                parsed_data["trace_data"] = trace_data

        return parsed_data

    def _log_scan_warnings(self, data: dict[str, Any]) -> None:
        """Log warnings for degraded scan results."""
        for warning in data.get("warnings", []):
            _log.warning("Antares: %s", warning)

        summary = data.get("summary", {})

        try:
            failed_workers = int(summary.get("failed_workers", 0))
        except (TypeError, ValueError):
            failed_workers = 0
        if failed_workers > 0:
            _log.warning(
                "Antares scan had %d failed worker(s)",
                failed_workers,
            )

        try:
            total_workers = int(summary.get("total_workers", 0))
        except (TypeError, ValueError):
            total_workers = 0
        if total_workers > 0 and failed_workers > total_workers // 2:
            _log.warning(
                "Antares: %d/%d CWE workers failed. "
                "A larger model (7B+) may improve results.",
                failed_workers,
                total_workers,
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

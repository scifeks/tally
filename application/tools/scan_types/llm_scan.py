"""LlmScan: runs LLM-based security scanning on configured repositories."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

from application.llm_scan.factory import create_llm_scan_backend
from application.llm_scan.prompts import build_scan_prompt
from application.llm_scan.tree_shaker import build_tree
from application.tools.scan_types.base import ScanType
from application.tools.scan_types.execution import dispatch_and_count_ingested
from application.tools.scan_types.models import ScanTypeConfig
from domain.pipeline import scan_events as se
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.models import ScanSummary
from domain.tools.scan_types.resources import IExecutionResources

logger = logging.getLogger(__name__)


class LlmScan(ScanType):
    """Run LLM-based security scanning on configured repositories."""

    def __init__(self, repo_names: list[str] | None = None) -> None:
        """Initialize LlmScan.

        Args:
            repo_names: Optional list of repo names to scan. If None, all
                active repos are scanned.

        """
        self._repo_names = repo_names

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        """Execute LLM-based security scan on configured repositories."""
        start = perf_counter()

        # Get repos to scan
        repos = config.repo_repo.list_active() if config.repo_repo else []
        if not repos:
            resources.display.print_status(
                "[yellow]No repositories configured; skipping[/yellow]"
            )
            return ScanSummary(
                total_tools_run=0,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=0,
                findings_by_tool={},
            )

        # Filter to requested repos if specified
        if self._repo_names:
            repos = [r for r in repos if r.name in self._repo_names]

        if not repos:
            resources.display.print_status(
                "[yellow]No matching repositories found[/yellow]"
            )
            return ScanSummary(
                total_tools_run=0,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=0,
                findings_by_tool={},
            )

        # Create backend and determine tool name
        repo_paths = {r.name: Path(r.path) for r in repos}
        backend, timeout_seconds = create_llm_scan_backend(
            app_root=Path(config.base_path),
            repo_paths=repo_paths,
        )

        # Detect tool name based on backend type
        backend_class_name = type(backend).__name__
        if "Claude" in backend_class_name:
            tool_name = "claudecode"
        else:
            tool_name = "opencode"

        resources.display.print_scan_header(f"LLM Scan: {config.project_name}")
        resources.event_sink.emit(
            se.SegmentStarted(
                run_id=config.run_id or 0,
                project_id=config.project_id,
                segment="llm",
                message="LLM scan started",
            )
        )

        all_results: list[ToolResult] = []
        total_run = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        # Scan each repo
        for repo in repos:
            resources.display.print_status(f"[bold]Repository:[/bold] {repo.name}")

            try:
                # Build directory tree
                tree = build_tree(Path(repo.path), max_depth=4)

                # Build prompt
                prompt = build_scan_prompt(tree, repo.name, str(repo.path))

                # Emit tool started event
                resources.display.print_running(tool_name, repo.name)
                resources.event_sink.emit(
                    se.ToolStarted(
                        run_id=config.run_id or 0,
                        project_id=config.project_id,
                        segment="llm",
                        repo=repo.name,
                        tool=tool_name,
                        message=f"LLM scan started for {repo.name}",
                    )
                )

                # Run the backend scan
                result_start = perf_counter()
                with backend.prepare_session(
                    project=config.project_name,
                    run_id=config.run_id or 0,
                    app_root=Path(config.base_path),
                ):
                    scan_result = backend.run_scan(
                        prompt,
                        timeout_seconds=timeout_seconds,
                        cwd=Path(config.base_path),
                    )
                duration = round(perf_counter() - result_start, 1)

                if scan_result.success:
                    # Convert findings to parsed_data format
                    parsed_data = {
                        "findings": [
                            {
                                "file_path": f.file_path,
                                "line_number": f.line_number or 0,
                                "description": f.description,
                                "severity": f.severity,
                                "confidence": f.confidence,
                                "finding_type": f.finding_type,
                                "segment": f.segment,
                                "reasoning": f.reasoning,
                                "remediation": f.remediation,
                                "rule_id": f.rule_id,
                                "cwe": f.cwe,
                                "attack_vector": f.attack_vector,
                                "code_snippet": f.code_snippet,
                            }
                            for f in scan_result.findings
                        ]
                    }

                    tool_result = ToolResult(
                        tool_name=tool_name,
                        success=True,
                        output=scan_result.raw_output,
                        parsed_data=parsed_data,
                        output_files={},
                        timestamp=ToolResult.now_iso(),
                        duration_seconds=duration,
                        finding_count=len(scan_result.findings),
                        repo=repo.name,
                    )

                    all_results.append(tool_result)
                    findings_by_tool[tool_name] = findings_by_tool.get(
                        tool_name, 0
                    ) + len(scan_result.findings)

                    # Dispatch for ingest pipeline
                    total_ingested += dispatch_and_count_ingested(
                        resources.event_bus,
                        ToolCompleted(
                            tool_result,
                            repo.name,
                            config.run_id,
                            config.project_name,
                            config.base_path,
                            repo=repo.name,
                        ),
                    )

                    resources.display.print_tool_line(
                        ToolDisplayRow(
                            f"{tool_name}/{repo.name}",
                            True,
                            False,
                            len(scan_result.findings),
                            duration,
                        )
                    )
                    findings_count = len(scan_result.findings)
                    resources.event_sink.emit(
                        se.ToolCompleted(
                            run_id=config.run_id or 0,
                            project_id=config.project_id,
                            segment="llm",
                            repo=repo.name,
                            tool=tool_name,
                            message=f"LLM scan complete: {findings_count} findings",
                            findings_count=findings_count,
                            duration=duration,
                            exit_code=0,
                        )
                    )
                    total_run += 1
                else:
                    # Scan failed
                    tool_result = ToolResult(
                        tool_name=tool_name,
                        success=False,
                        output=scan_result.raw_output or scan_result.error or "",
                        parsed_data={},
                        output_files={},
                        timestamp=ToolResult.now_iso(),
                        duration_seconds=duration,
                        finding_count=0,
                        repo=repo.name,
                    )

                    all_results.append(tool_result)

                    resources.display.print_tool_line(
                        ToolDisplayRow(
                            f"{tool_name}/{repo.name}",
                            False,
                            False,
                            0,
                            duration,
                        )
                    )
                    error_msg = f"LLM scan failed for {repo.name}: {scan_result.error}"
                    resources.event_sink.emit(
                        se.ToolFailed(
                            run_id=config.run_id or 0,
                            project_id=config.project_id,
                            segment="llm",
                            repo=repo.name,
                            tool=tool_name,
                            message=error_msg,
                            exit_code=1,
                            duration=duration,
                        )
                    )
                    total_failed += 1

            except Exception as exc:
                logger.exception("LLM scan failed for repo %s", repo.name)
                duration = round(perf_counter() - result_start, 1)

                resources.display.print_tool_line(
                    ToolDisplayRow(
                        f"{tool_name}/{repo.name}",
                        False,
                        False,
                        0,
                        duration,
                    )
                )
                resources.event_sink.emit(
                    se.ToolFailed(
                        run_id=config.run_id or 0,
                        project_id=config.project_id,
                        segment="llm",
                        repo=repo.name,
                        tool=tool_name,
                        message=f"LLM scan failed for {repo.name}: {exc!s}",
                        exit_code=1,
                        duration=duration,
                    )
                )
                total_failed += 1

        duration = round(perf_counter() - start, 1)
        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=r.finding_count,
                duration_seconds=r.duration_seconds,
                repo=r.repo,
            )
            for r in all_results
        ]
        resources.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=0,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
        resources.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )

        resources.event_sink.emit(
            se.SegmentCompleted(
                run_id=config.run_id or 0,
                project_id=config.project_id,
                segment="llm",
                message="LLM scan completed",
                findings_count=total_ingested,
            )
        )

        return summary

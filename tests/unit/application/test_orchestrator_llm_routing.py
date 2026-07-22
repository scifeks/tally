"""Unit tests for ScanOrchestrator LLM domain routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.ports.scan_event_sink import NullScanEventSink
from application.tools.orchestrator import ScanOrchestrator
from domain.tools.scan_types.models import ScanSummary


def _empty_summary() -> ScanSummary:
    return ScanSummary(
        total_tools_run=0,
        total_tools_skipped=0,
        total_tools_failed=0,
        results=[],
        duration_seconds=0.0,
        findings_ingested=0,
        findings_by_tool={},
    )


def _make_orchestrator(
    *,
    run_id: int | None = 1,
    project_id: int | None = 42,
    registry_tools: list[str] | None = None,
    sink: NullScanEventSink | None = None,
) -> ScanOrchestrator:
    tool_registry = MagicMock()
    tool_registry.list_tool_names.return_value = registry_tools or [
        "semgrep",
        "gitleaks",
        "zap",
    ]
    with (
        patch("core.config.manager.ConfigManager"),
        patch("application.tools.orchestrator._build_tool_execution_config"),
    ):
        return ScanOrchestrator(
            project="test-project",
            tool_registry=tool_registry,
            tool_executor=MagicMock(base_path="/tmp"),
            event_bus=MagicMock(),
            prompt=MagicMock(),
            run_id=run_id,
            event_sink=sink,
            run_repository=None,
            project_id=project_id,
        )


@patch("application.tools.scan_types.llm_scan.LlmScan")
def test_llm_domain_routes_to_llm_scan(mock_llm_scan: MagicMock) -> None:
    """When domains=['llm'], LlmScan is invoked with repo_names."""
    mock_llm_scan.return_value.execute.return_value = _empty_summary()
    o = _make_orchestrator()

    result = o.run_scoped_scan(
        repo_names=["repo-a", "repo-b"],
        domains=["llm"],
    )

    assert result is not None
    mock_llm_scan.assert_called_once_with(repo_names=["repo-a", "repo-b"])
    mock_llm_scan.return_value.execute.assert_called_once()


@patch("application.tools.scan_types.llm_scan.LlmScan")
def test_llm_domain_with_no_repos_routes_to_llm_scan(
    mock_llm_scan: MagicMock,
) -> None:
    """When domains=['llm'] with no repo_names, LlmScan is invoked."""
    mock_llm_scan.return_value.execute.return_value = _empty_summary()
    o = _make_orchestrator()

    result = o.run_scoped_scan(domains=["llm"])

    assert result is not None
    mock_llm_scan.assert_called_once_with(repo_names=None)


@patch(
    "application.tools.scan_types.execution.ordered_repo_tools",
    side_effect=lambda s, _r: sorted(s),
)
@patch("application.tools.orchestrator.ToolOnAllReposScan")
@patch("application.rag.ingestor.get_tool_domain")
def test_non_llm_domain_uses_tool_filtering(
    mock_domain: MagicMock,
    mock_toa: MagicMock,
    _mock_order: MagicMock,
) -> None:
    """Non-LLM domains still filter tools normally."""
    mock_toa.return_value.execute.return_value = _empty_summary()
    mock_domain.side_effect = lambda t: {
        "semgrep": "code",
        "gitleaks": "code",
    }.get(t, "web")
    o = _make_orchestrator()

    o.run_scoped_scan(domains=["code"])

    tools_called = [c.args[0] for c in mock_toa.call_args_list]
    assert tools_called == ["gitleaks", "semgrep"]
    assert "zap" not in tools_called


@patch("application.tools.orchestrator.FullScan")
def test_llm_domain_ignores_tool_names_filter(mock_full: MagicMock) -> None:
    """When domains=['llm'], tool_names filter is ignored."""
    mock_full.return_value.execute.return_value = _empty_summary()
    o = _make_orchestrator()

    # tool_names should be ignored when domains=['llm']
    with patch("application.tools.scan_types.llm_scan.LlmScan") as mock_llm_scan:
        mock_llm_scan.return_value.execute.return_value = _empty_summary()

        o.run_scoped_scan(
            tool_names=["semgrep"],
            domains=["llm"],
        )

        mock_llm_scan.assert_called_once()
        # Full scan should not be called for LLM domain
        assert not mock_full.called

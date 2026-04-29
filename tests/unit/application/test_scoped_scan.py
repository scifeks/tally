"""Unit tests for ScanOrchestrator.run_scoped_scan.

run_scoped_scan is the unified entry point shared by the REPL and HTTP API
for "scope a scan to specific repos / tools / domains". It wraps the
existing scan-type strategies and emits one RunStarted/RunCompleted pair
around the whole scoped run regardless of how many internal pairs fire.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.locking.cancellation import CancellationToken
from application.ports.scan_event_sink import NullScanEventSink
from application.tools.orchestrator import ScanOrchestrator
from domain.pipeline import scan_events as se
from domain.tools.scan_types.models import ScanSummary


class _RecordingSink(NullScanEventSink):
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:  # type: ignore[override]
        self.events.append(event)


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


def _summary(findings_by_tool: dict[str, int]) -> ScanSummary:
    return ScanSummary(
        total_tools_run=len(findings_by_tool),
        total_tools_skipped=0,
        total_tools_failed=0,
        results=[],
        duration_seconds=0.0,
        findings_ingested=sum(findings_by_tool.values()),
        findings_by_tool=findings_by_tool,
    )


def _make_orchestrator(
    *,
    run_id: int | None = 1,
    project_id: int | None = 42,
    registry_tools: list[str] | None = None,
    sink: NullScanEventSink | None = None,
    cancel: CancellationToken | None = None,
) -> ScanOrchestrator:
    tool_registry = MagicMock()
    tool_registry.list_tool_names.return_value = registry_tools or [
        "semgrep",
        "gitleaks",
        "zap",
    ]
    with patch("core.config.manager.ConfigManager"):
        return ScanOrchestrator(
            project="test-project",
            tool_registry=tool_registry,
            tool_executor=MagicMock(base_path="/tmp"),
            event_bus=MagicMock(),
            prompt=MagicMock(),
            run_id=run_id,
            event_sink=sink,
            cancel_token=cancel,
            run_repository=None,
            project_id=project_id,
        )


@patch("application.tools.orchestrator.ToolOnRepoScan")
def test_repos_and_tools_runs_nested_loop(mock_tor: MagicMock) -> None:
    mock_tor.return_value.execute.return_value = _summary({"semgrep": 1})
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    o.run_scoped_scan(
        repo_names=["repo-a", "repo-b"],
        tool_names=["semgrep", "gitleaks"],
    )

    pair_args = [c.args for c in mock_tor.call_args_list]
    assert pair_args == [
        ("semgrep", "repo-a"),
        ("gitleaks", "repo-a"),
        ("semgrep", "repo-b"),
        ("gitleaks", "repo-b"),
    ]


@patch("application.tools.orchestrator.RepoScan")
def test_repos_only_loops_repo_scan(mock_rs: MagicMock) -> None:
    mock_rs.return_value.execute.return_value = _empty_summary()
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    o.run_scoped_scan(
        repo_names=["repo-a", "repo-b"],
        skip_tools={"zap"},
    )

    repos_called = [c.args[0] for c in mock_rs.call_args_list]
    assert repos_called == ["repo-a", "repo-b"]
    # exclude_tools is forwarded as the second positional arg.
    for c in mock_rs.call_args_list:
        assert c.args[1] == {"zap"}


@patch("application.tools.orchestrator.ToolOnAllReposScan")
def test_tools_only_loops_tool_on_all_repos(mock_toa: MagicMock) -> None:
    mock_toa.return_value.execute.return_value = _empty_summary()
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    o.run_scoped_scan(tool_names=["semgrep", "gitleaks"])

    tools_called = [c.args[0] for c in mock_toa.call_args_list]
    assert tools_called == ["semgrep", "gitleaks"]


@patch("application.tools.orchestrator.FullScan")
def test_no_scope_falls_to_full_scan(mock_full: MagicMock) -> None:
    mock_full.return_value.execute.return_value = _empty_summary()
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    o.run_scoped_scan(skip_tools={"zap"})

    assert mock_full.called
    args = mock_full.call_args.args
    assert args[0] == []
    assert args[1] == {"zap"}


@patch("application.rag.ingestor.get_tool_domain")
@patch("application.tools.orchestrator.ToolOnAllReposScan")
def test_domains_filter_effective_tools(
    mock_toa: MagicMock, mock_domain: MagicMock
) -> None:
    mock_toa.return_value.execute.return_value = _empty_summary()
    # semgrep -> code, zap -> web, gitleaks -> code
    mock_domain.side_effect = lambda t: {"semgrep": "code", "gitleaks": "code"}.get(
        t, "web"
    )
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    o.run_scoped_scan(domains=["code"])

    tools_called = [c.args[0] for c in mock_toa.call_args_list]
    assert tools_called == ["semgrep", "gitleaks"]
    assert "zap" not in tools_called


@patch("application.tools.orchestrator.ToolOnRepoScan")
def test_emits_single_run_started_completed(mock_tor: MagicMock) -> None:
    mock_tor.return_value.execute.return_value = _summary({"semgrep": 3})
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    o.run_scoped_scan(
        repo_names=["repo-a", "repo-b"],
        tool_names=["semgrep"],
    )

    types = [type(e) for e in sink.events]
    # Despite 2 inner ToolOnRepoScan executions, only one outer run pair.
    assert types == [se.RunStarted, se.RunCompleted]
    started, completed = sink.events
    assert started.run_id == 1
    assert started.project_id == 42
    assert completed.run_id == 1
    assert completed.project_id == 42
    # findings aggregated across pairs (3 + 3 = 6)
    assert completed.findings_count == 6


@patch("application.tools.orchestrator.ToolOnRepoScan")
def test_findings_by_tool_aggregated(mock_tor: MagicMock) -> None:
    mock_tor.return_value.execute.side_effect = [
        _summary({"semgrep": 1}),
        _summary({"semgrep": 2}),
        _summary({"gitleaks": 4}),
        _summary({"gitleaks": 5}),
    ]
    sink = _RecordingSink()
    o = _make_orchestrator(sink=sink)

    summary = o.run_scoped_scan(
        repo_names=["repo-a", "repo-b"],
        tool_names=["semgrep", "gitleaks"],
    )

    assert summary.findings_by_tool == {"semgrep": 3, "gitleaks": 9}

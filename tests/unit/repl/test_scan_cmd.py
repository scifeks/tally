"""Tests for the refactored flag-based scan command."""

from unittest.mock import MagicMock, call, patch

from application.repl.commands.scan_commands import ScanCommands

MOCK_TOOLS = ["gitleaks", "semgrep", "nmap", "zap", "pip-audit"]


def _make_repo(name: str = "myrepo") -> MagicMock:
    repo = MagicMock()
    repo.name = name
    return repo


def _run(
    args: list[str],
    tools: list[str] = MOCK_TOOLS,
    repos: list[MagicMock] | None = None,
    active_project: str = "proj",
) -> tuple[MagicMock, MagicMock]:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/test"
    repos = repos or [_make_repo()]
    repl.config.load_repositories.return_value = repos

    mock_orchestrator = MagicMock()

    sc = ScanCommands(repl)
    with (
        patch("application.repl.commands.scan_commands.tool_registry") as mock_reg,
        patch.object(sc, "_make_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
            return_value="/tmp/oas3.json",
        ),
    ):
        mock_reg.list_tool_names.return_value = tools
        sc.cmd_scan("scan", args)

    return repl, mock_orchestrator


def test_scan_no_args_calls_run_full_scan() -> None:
    _repl, orchestrator = _run([])
    assert orchestrator.run_full_scan.called


def test_scan_repo_calls_run_repo_scan() -> None:
    _repl, orchestrator = _run(["--repo=myrepo"])
    assert orchestrator.run_repo_scan.call_args == call(repo_name="myrepo")


def test_scan_tool_single_calls_run_tool_on_all_repos() -> None:
    _repl, orchestrator = _run(["--tool=semgrep"])
    assert orchestrator.run_tool_on_all_repos.call_args == call(
        "semgrep", remaining_peers=0
    )


def test_scan_tool_comma_list_calls_for_each_tool() -> None:
    _repl, orchestrator = _run(["--tool=semgrep,gitleaks"])
    calls = orchestrator.run_tool_on_all_repos.call_args_list
    called_tools = [c.args[0] for c in calls]
    assert "semgrep" in called_tools
    assert "gitleaks" in called_tools


def test_scan_domain_code_runs_only_code_tools() -> None:
    _repl, orchestrator = _run(["--domain=code"])
    calls = orchestrator.run_tool_on_all_repos.call_args_list
    called_tools = [c.args[0] for c in calls]
    assert "nmap" not in called_tools
    assert "zap" not in called_tools


def test_scan_domain_code_web_runs_both_domain_tools() -> None:
    _repl, orchestrator = _run(["--domain=code,web"])
    calls = orchestrator.run_tool_on_all_repos.call_args_list
    called_tools = [c.args[0] for c in calls]
    assert "zap" in called_tools
    assert any(t in called_tools for t in ("semgrep", "gitleaks", "pip-audit"))


def test_scan_invalid_tool_prints_error() -> None:
    repl, orchestrator = _run(["--tool=badtool"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown tool" in printed
    assert not orchestrator.run_full_scan.called
    assert not orchestrator.run_repo_scan.called
    assert not orchestrator.run_tool_on_all_repos.called


def test_scan_invalid_domain_prints_error() -> None:
    repl, orchestrator = _run(["--domain=badtype"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown domain" in printed
    assert not orchestrator.run_full_scan.called


def test_scan_old_positional_syntax_rejected() -> None:
    repl, orchestrator = _run(["repo", "myrepo"])
    printed = repl.console.print.call_args[0][0]
    assert "Unrecognized" in printed
    assert not orchestrator.run_full_scan.called
    assert not orchestrator.run_repo_scan.called
    assert not orchestrator.run_tool_on_all_repos.called
    assert not orchestrator.run_tool_on_repo.called

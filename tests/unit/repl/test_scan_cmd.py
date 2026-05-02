"""Tests for the refactored flag-based scan command.

After the hexagonal cleanup the REPL calls ``ScanService.start_scan``
once with the parsed scope (repos / tools / domains / skip_tools).
These tests assert the kwargs the REPL passes to ``start_scan``, not
the orchestrator-level fan-out (which is covered separately).
"""

from unittest.mock import MagicMock, patch

from application.repl.commands.scan_commands import ScanCommands
from domain.projects.entry import ProjectRow

MOCK_TOOLS = ["gitleaks", "semgrep", "nmap", "zap", "pip-audit"]


def _make_repo(name: str = "myrepo") -> MagicMock:
    repo = MagicMock()
    repo.name = name
    # crawl_enabled=False keeps the repo out of the DAST-without-discovery
    # warning path, which would otherwise prompt for stdin input under
    # pytest's captured-stdin environment.
    repo.crawl_enabled = False
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
    repl.project_registry.resolve_by_name.return_value = ProjectRow(
        id=1, name=active_project, path="/tmp/test", created_at="2026-05-02T00:00:00Z"
    )
    repos = repos or [_make_repo()]

    mock_summary = MagicMock(findings_by_tool={})
    mock_handle = MagicMock(run_id=1)
    mock_handle.result.result.return_value = mock_summary

    mock_service = MagicMock()
    mock_service.start_scan.return_value = mock_handle

    sc = ScanCommands(repl)
    with (
        patch("application.repl.commands.scan_commands.tool_registry") as mock_reg,
        patch(
            "application.repl.commands.scan_commands.get_scan_service",
            return_value=mock_service,
        ),
        patch.object(ScanCommands, "_active_repos", return_value=repos),
    ):
        mock_reg.list_tool_names.return_value = tools
        sc.cmd_scan("scan", args)

    return repl, mock_service


def _scoped_kwargs(service: MagicMock) -> dict:
    """Return the kwargs that ScanService.start_scan was called with."""
    assert service.start_scan.called
    return service.start_scan.call_args.kwargs


def test_scan_no_args_invokes_run_scoped_scan_with_no_scope() -> None:
    _repl, orchestrator = _run([])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_ids"] == ()
    assert kwargs["tool_ids"] == ()
    assert kwargs["skip_tool_ids"] == ()


def test_scan_repo_passes_repo_name() -> None:
    _repl, orchestrator = _run(["--repo=myrepo"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_ids"] == ("myrepo",)
    assert kwargs["tool_ids"] == ()


def test_scan_multiple_repos_passes_all_names() -> None:
    repos = [_make_repo("repo-a"), _make_repo("repo-b")]
    _repl, orchestrator = _run(["--repo=repo-a,repo-b"], repos=repos)
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_ids"] == ("repo-a", "repo-b")
    assert kwargs["tool_ids"] == ()


def test_scan_multiple_repos_unknown_repo_prints_error() -> None:
    repos = [_make_repo("repo-a")]
    repl, orchestrator = _run(["--repo=repo-a,nope"], repos=repos)
    printed = repl.console.print.call_args[0][0]
    assert "Unknown repository" in printed
    assert "nope" in printed
    assert not orchestrator.start_scan.called


def test_scan_multiple_repos_with_tool_passes_both_dimensions() -> None:
    repos = [_make_repo("repo-a"), _make_repo("repo-b")]
    _repl, orchestrator = _run(["--repo=repo-a,repo-b", "--tool=semgrep"], repos=repos)
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_ids"] == ("repo-a", "repo-b")
    assert kwargs["tool_ids"] == ("semgrep",)


def test_scan_tool_single_passes_tool_name() -> None:
    _repl, orchestrator = _run(["--tool=semgrep"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_ids"] == ()
    assert kwargs["tool_ids"] == ("semgrep",)


def test_scan_tool_comma_list_passes_all_tools() -> None:
    _repl, orchestrator = _run(["--tool=semgrep,gitleaks"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["tool_ids"] == ("semgrep", "gitleaks")


def test_scan_domain_filters_effective_tools_via_repl() -> None:
    # The REPL pre-resolves effective_tools by intersecting with domain.
    # When --domain alone is given, run_scoped_scan receives
    # tool_names=<filtered list>, domains=None.
    with patch(
        "application.rag.ingestor.get_tool_domain",
        side_effect=lambda t: (
            "code" if t in {"semgrep", "gitleaks", "pip-audit"} else "web"
        ),
    ):
        _repl, orchestrator = _run(["--domain=code"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["tool_ids"]
    assert "nmap" not in kwargs["tool_ids"]
    assert "zap" not in kwargs["tool_ids"]


def test_scan_domain_code_web_includes_both_domain_tools() -> None:
    with patch(
        "application.rag.ingestor.get_tool_domain",
        side_effect=lambda t: (
            "code" if t in {"semgrep", "gitleaks", "pip-audit"} else "web"
        ),
    ):
        _repl, orchestrator = _run(["--domain=code,web"])
    kwargs = _scoped_kwargs(orchestrator)
    tools = list(kwargs["tool_ids"])
    assert "zap" in tools
    assert any(t in tools for t in ("semgrep", "gitleaks", "pip-audit"))


def test_scan_invalid_tool_prints_error() -> None:
    repl, orchestrator = _run(["--tool=badtool"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown tool" in printed
    assert not orchestrator.start_scan.called


def test_scan_invalid_domain_prints_error() -> None:
    repl, orchestrator = _run(["--domain=badtype"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown domain" in printed
    assert not orchestrator.start_scan.called


def test_scan_old_positional_syntax_rejected() -> None:
    repl, orchestrator = _run(["repo", "myrepo"])
    printed = repl.console.print.call_args[0][0]
    assert "Unrecognized" in printed
    assert not orchestrator.start_scan.called


# ------------------------------------------------------------------
# --skip-tools tests
# ------------------------------------------------------------------


def test_skip_tools_passes_skip_tools_set() -> None:
    _repl, orchestrator = _run(["--skip-tools=zap,nmap"])
    kwargs = _scoped_kwargs(orchestrator)
    assert set(kwargs["skip_tool_ids"]) == {"zap", "nmap"}
    assert kwargs["tool_ids"] == ()


def test_skip_tools_single_passes_skip_tools_set() -> None:
    _repl, orchestrator = _run(["--skip-tools=zap"])
    kwargs = _scoped_kwargs(orchestrator)
    assert set(kwargs["skip_tool_ids"]) == {"zap"}


def test_skip_tools_invalid_tool_prints_error() -> None:
    repl, orchestrator = _run(["--skip-tools=notreal"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown tool" in printed
    assert not orchestrator.start_scan.called


def test_skip_tools_and_tool_flag_are_mutually_exclusive() -> None:
    repl, orchestrator = _run(["--tool=semgrep", "--skip-tools=zap"])
    printed = repl.console.print.call_args[0][0]
    assert "mutually exclusive" in printed
    assert not orchestrator.start_scan.called


def test_skip_tools_with_repo_passes_both() -> None:
    repos = [_make_repo("repo-a")]
    _repl, orchestrator = _run(["--repo=repo-a", "--skip-tools=zap,nmap"], repos=repos)
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_ids"] == ("repo-a",)
    assert set(kwargs["skip_tool_ids"]) == {"zap", "nmap"}


# ------------------------------------------------------------------
# --skip-enrichment tests
# ------------------------------------------------------------------


def test_skip_enrichment_flag_passes_true_to_start_scan() -> None:
    _repl, service = _run(["--skip-enrichment"])
    kwargs = _scoped_kwargs(service)
    assert kwargs.get("skip_enrichment") is True


def test_no_skip_enrichment_flag_defaults_to_false() -> None:
    _repl, service = _run([])
    kwargs = _scoped_kwargs(service)
    assert kwargs.get("skip_enrichment") is False


def test_skip_enrichment_flag_is_not_unrecognized() -> None:
    repl, _service = _run(["--skip-enrichment"])
    # If flag were unrecognized, console.print would contain "Unrecognized".
    for call_args in repl.console.print.call_args_list:
        text = call_args[0][0] if call_args[0] else ""
        assert "Unrecognized" not in str(text)


def test_skip_enrichment_combined_with_repo_flag() -> None:
    repos = [_make_repo("repo-a")]
    _repl, service = _run(["--repo=repo-a", "--skip-enrichment"], repos=repos)
    kwargs = _scoped_kwargs(service)
    assert kwargs.get("skip_enrichment") is True

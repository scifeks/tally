"""Tests for the refactored flag-based scan command.

After the hexagonal cleanup the REPL no longer dispatches to individual
``run_*`` methods directly. It calls ``orchestrator.run_scoped_scan`` once
with the parsed scope (repos / tools / domains / skip_tools) and the
orchestrator decides which scan-type strategies to invoke. These tests
assert the kwargs the REPL passes to ``run_scoped_scan``, not the
strategy fan-out (which is covered by orchestrator-level tests).
"""

from unittest.mock import MagicMock, patch

from application.repl.commands.scan_commands import ScanCommands

MOCK_TOOLS = ["gitleaks", "semgrep", "nmap", "zap", "pip-audit"]


def _make_repo(name: str = "myrepo") -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.oas3_path = "/tmp/oas3.json"
    repo.merged_oas3_path = "/tmp/merged_oas3.json"
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
    mock_orchestrator.run_scoped_scan.return_value = MagicMock(findings_by_tool={})

    sc = ScanCommands(repl)
    with (
        patch("application.repl.commands.scan_commands.tool_registry") as mock_reg,
        patch.object(sc, "_make_orchestrator", return_value=mock_orchestrator),
    ):
        mock_reg.list_tool_names.return_value = tools
        sc.cmd_scan("scan", args)

    return repl, mock_orchestrator


def _scoped_kwargs(orchestrator: MagicMock) -> dict:
    """Return the kwargs that run_scoped_scan was called with."""
    assert orchestrator.run_scoped_scan.called
    return orchestrator.run_scoped_scan.call_args.kwargs


def test_scan_no_args_invokes_run_scoped_scan_with_no_scope() -> None:
    _repl, orchestrator = _run([])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_names"] is None
    assert kwargs["tool_names"] is None
    assert kwargs["skip_tools"] is None


def test_scan_repo_passes_repo_name() -> None:
    _repl, orchestrator = _run(["--repo=myrepo"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_names"] == ["myrepo"]
    assert kwargs["tool_names"] is None


def test_scan_multiple_repos_passes_all_names() -> None:
    repos = [_make_repo("repo-a"), _make_repo("repo-b")]
    _repl, orchestrator = _run(["--repo=repo-a,repo-b"], repos=repos)
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_names"] == ["repo-a", "repo-b"]
    assert kwargs["tool_names"] is None


def test_scan_multiple_repos_unknown_repo_prints_error() -> None:
    repos = [_make_repo("repo-a")]
    repl, orchestrator = _run(["--repo=repo-a,nope"], repos=repos)
    printed = repl.console.print.call_args[0][0]
    assert "Unknown repository" in printed
    assert "nope" in printed
    assert not orchestrator.run_scoped_scan.called


def test_scan_multiple_repos_with_tool_passes_both_dimensions() -> None:
    repos = [_make_repo("repo-a"), _make_repo("repo-b")]
    _repl, orchestrator = _run(["--repo=repo-a,repo-b", "--tool=semgrep"], repos=repos)
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_names"] == ["repo-a", "repo-b"]
    assert kwargs["tool_names"] == ["semgrep"]


def test_scan_tool_single_passes_tool_name() -> None:
    _repl, orchestrator = _run(["--tool=semgrep"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_names"] is None
    assert kwargs["tool_names"] == ["semgrep"]


def test_scan_tool_comma_list_passes_all_tools() -> None:
    _repl, orchestrator = _run(["--tool=semgrep,gitleaks"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["tool_names"] == ["semgrep", "gitleaks"]


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
    assert kwargs["tool_names"] is not None
    assert "nmap" not in kwargs["tool_names"]
    assert "zap" not in kwargs["tool_names"]


def test_scan_domain_code_web_includes_both_domain_tools() -> None:
    with patch(
        "application.rag.ingestor.get_tool_domain",
        side_effect=lambda t: (
            "code" if t in {"semgrep", "gitleaks", "pip-audit"} else "web"
        ),
    ):
        _repl, orchestrator = _run(["--domain=code,web"])
    kwargs = _scoped_kwargs(orchestrator)
    tools = kwargs["tool_names"] or []
    assert "zap" in tools
    assert any(t in tools for t in ("semgrep", "gitleaks", "pip-audit"))


def test_scan_invalid_tool_prints_error() -> None:
    repl, orchestrator = _run(["--tool=badtool"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown tool" in printed
    assert not orchestrator.run_scoped_scan.called


def test_scan_invalid_domain_prints_error() -> None:
    repl, orchestrator = _run(["--domain=badtype"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown domain" in printed
    assert not orchestrator.run_scoped_scan.called


def test_scan_old_positional_syntax_rejected() -> None:
    repl, orchestrator = _run(["repo", "myrepo"])
    printed = repl.console.print.call_args[0][0]
    assert "Unrecognized" in printed
    assert not orchestrator.run_scoped_scan.called


# ------------------------------------------------------------------
# --skip-tools tests
# ------------------------------------------------------------------


def test_skip_tools_passes_skip_tools_set() -> None:
    _repl, orchestrator = _run(["--skip-tools=zap,nmap"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["skip_tools"] == {"zap", "nmap"}
    assert kwargs["tool_names"] is None


def test_skip_tools_single_passes_skip_tools_set() -> None:
    _repl, orchestrator = _run(["--skip-tools=zap"])
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["skip_tools"] == {"zap"}


def test_skip_tools_invalid_tool_prints_error() -> None:
    repl, orchestrator = _run(["--skip-tools=notreal"])
    printed = repl.console.print.call_args[0][0]
    assert "Unknown tool" in printed
    assert not orchestrator.run_scoped_scan.called


def test_skip_tools_and_tool_flag_are_mutually_exclusive() -> None:
    repl, orchestrator = _run(["--tool=semgrep", "--skip-tools=zap"])
    printed = repl.console.print.call_args[0][0]
    assert "mutually exclusive" in printed
    assert not orchestrator.run_scoped_scan.called


def test_skip_tools_with_repo_passes_both() -> None:
    repos = [_make_repo("repo-a")]
    _repl, orchestrator = _run(["--repo=repo-a", "--skip-tools=zap,nmap"], repos=repos)
    kwargs = _scoped_kwargs(orchestrator)
    assert kwargs["repo_names"] == ["repo-a"]
    assert kwargs["skip_tools"] == {"zap", "nmap"}


# ------------------------------------------------------------------
# --skip-enrichment tests
# ------------------------------------------------------------------


def _run_capture_orchestrator_kwargs(
    args: list[str],
    tools: list[str] = MOCK_TOOLS,
    repos: list[MagicMock] | None = None,
    active_project: str = "proj",
) -> dict:
    """Like _run but returns the kwargs _make_orchestrator was called with."""
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/test"
    repos = repos or [_make_repo()]
    repl.config.load_repositories.return_value = repos

    mock_orchestrator = MagicMock()
    mock_orchestrator.run_scoped_scan.return_value = MagicMock(findings_by_tool={})
    captured: dict = {}

    sc = ScanCommands(repl)

    def _capture_make_orchestrator(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return mock_orchestrator

    with (
        patch("application.repl.commands.scan_commands.tool_registry") as mock_reg,
        patch.object(sc, "_make_orchestrator", side_effect=_capture_make_orchestrator),
    ):
        mock_reg.list_tool_names.return_value = tools
        sc.cmd_scan("scan", args)

    return captured


def test_skip_enrichment_flag_passes_true_to_make_orchestrator() -> None:
    kwargs = _run_capture_orchestrator_kwargs(["--skip-enrichment"])
    assert kwargs.get("skip_enrichment") is True


def test_no_skip_enrichment_flag_defaults_to_false() -> None:
    kwargs = _run_capture_orchestrator_kwargs([])
    assert kwargs.get("skip_enrichment") is False


def test_skip_enrichment_flag_is_not_unrecognized() -> None:
    repl, _orchestrator = _run(["--skip-enrichment"])
    # If flag were unrecognized, console.print would contain "Unrecognized".
    for call_args in repl.console.print.call_args_list:
        text = call_args[0][0] if call_args[0] else ""
        assert "Unrecognized" not in str(text)


def test_skip_enrichment_combined_with_repo_flag() -> None:
    repos = [_make_repo("repo-a")]
    kwargs = _run_capture_orchestrator_kwargs(
        ["--repo=repo-a", "--skip-enrichment"], repos=repos
    )
    assert kwargs.get("skip_enrichment") is True

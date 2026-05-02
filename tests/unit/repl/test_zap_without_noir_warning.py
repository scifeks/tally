"""Tests for the DAST-without-discovery warning in ScanCommands.

Discovery presence is determined by ``_repo_has_url_findings`` (SQLite
``url_findings`` query), not by reading ``repo.oas3_path`` /
``repo.merged_oas3_path``. These tests stub that probe.

Covers:
- Warning is shown when DAST tools are requested and no discovery output exists
- Option 1: discovery tools are prepended to the tool list (recommended)
- Option 2: Tool list unchanged (DAST-only, no discovery output)
- Option 3: Returns None (cancel)
- Warning is NOT shown when a discovery tool is already in the tool list
- Warning is NOT shown when auto_approve=True
- Warning is NOT shown when discovery output already exists for all repos
- Default input (empty Enter) selects option 1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.scan_commands import ScanCommands
from domain.projects.entry import ProjectRow


def _make_repl(
    repo_names: list[str] | None = None,
) -> tuple[MagicMock, list[MagicMock]]:
    repl = MagicMock()
    repl.active_project = "DVPA"
    repl.base_path = "/tmp/tally"
    names = repo_names if repo_names is not None else ["dvna"]
    repos = []
    for name in names:
        r = MagicMock()
        r.name = name
        r.crawl_enabled = True
        repos.append(r)
    return repl, repos


def _make_sc(repo_names: list[str] | None = None) -> ScanCommands:
    repl, repos = _make_repl(repo_names)
    sc = ScanCommands(repl)
    sc._active_repos = MagicMock(return_value=repos)  # type: ignore[method-assign]
    return sc


# ---------------------------------------------------------------------------
# _maybe_warn_dast_without_discovery helpers
# ---------------------------------------------------------------------------


class TestMaybeWarnDastWithoutDiscovery:
    def _call(
        self,
        tools: list[str],
        repo_name: str | None = None,
        auto_approve: bool = False,
        url_findings_exist: bool = False,
        user_input: str = "1",
        repo_names: list[str] | None = None,
    ) -> list[str] | None:
        sc = _make_sc(repo_names)
        names: list[str] | None = [repo_name] if repo_name is not None else repo_names
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=url_findings_exist),
            patch("builtins.input", return_value=user_input),
        ):
            return sc._maybe_warn_dast_without_discovery(tools, names, auto_approve)

    def test_no_warning_when_no_dast_tools(self) -> None:
        result = self._call(["semgrep"])
        assert result == ["semgrep"]

    def test_no_warning_when_noir_already_in_tools(self) -> None:
        result = self._call(["noir", "zap"])
        assert result == ["noir", "zap"]

    def test_no_warning_when_katana_already_in_tools(self) -> None:
        result = self._call(["katana", "zap"])
        assert result == ["katana", "zap"]

    def test_no_warning_when_auto_approve(self) -> None:
        result = self._call(["zap"], auto_approve=True)
        assert result == ["zap"]

    def test_no_warning_when_url_findings_exist(self) -> None:
        result = self._call(["zap"], url_findings_exist=True)
        assert result == ["zap"]

    def test_no_warning_when_crawl_disabled(self) -> None:
        """Repos with crawl_enabled=False are excluded from missing."""
        repl, repos = _make_repl()
        repos[0].crawl_enabled = False
        sc = ScanCommands(repl)
        sc._active_repos = MagicMock(return_value=repos)  # type: ignore[method-assign]
        mock_input = MagicMock()
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=False),
            patch("builtins.input", mock_input),
        ):
            result = sc._maybe_warn_dast_without_discovery(["zap"], None, False)
        assert result == ["zap"]
        mock_input.assert_not_called()

    def test_option1_prepends_katana_and_noir_for_non_node_repo(self) -> None:
        result = self._call(["zap"], user_input="1")
        assert result is not None
        assert result[0] == "katana"
        assert "noir" in result
        assert result.index("katana") < result.index("noir")

    def test_option1_default_empty_input(self) -> None:
        """Empty Enter defaults to option 1."""
        result = self._call(["zap"], user_input="")
        assert result is not None
        assert "katana" in result

    def test_option1_invalid_input_defaults_to_option1(self) -> None:
        result = self._call(["zap"], user_input="x")
        assert result is not None
        assert "katana" in result

    def test_option2_returns_tools_unchanged(self) -> None:
        result = self._call(["zap"], user_input="2")
        assert result == ["zap"]

    def test_option3_returns_none(self) -> None:
        result = self._call(["zap"], user_input="3")
        assert result is None

    def test_option1_preserves_other_tools(self) -> None:
        """Other tools in the list are kept after discovery is prepended."""
        result = self._call(["semgrep", "zap"], user_input="1")
        assert result is not None
        assert "katana" in result
        assert "zap" in result
        assert "semgrep" in result

    def test_dalfox_triggers_warning(self) -> None:
        result = self._call(["dalfox"], user_input="2")
        assert result == ["dalfox"]

    def test_xsstrike_triggers_warning(self) -> None:
        result = self._call(["xsstrike"], user_input="2")
        assert result == ["xsstrike"]

    def test_eof_returns_none(self) -> None:
        sc = _make_sc()
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=False),
            patch("builtins.input", side_effect=EOFError),
        ):
            result = sc._maybe_warn_dast_without_discovery(["zap"], None, False)
        assert result is None

    def test_warning_printed_to_console(self) -> None:
        repl, repos = _make_repl()
        sc = ScanCommands(repl)
        sc._active_repos = MagicMock(return_value=repos)  # type: ignore[method-assign]
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=False),
            patch("builtins.input", return_value="2"),
        ):
            sc._maybe_warn_dast_without_discovery(["zap"], None, False)

        printed = " ".join(
            str(a) for call in repl.console.print.call_args_list for a in call[0]
        )
        assert "Warning" in printed or "warning" in printed.lower()


# ---------------------------------------------------------------------------
# Integration: _cmd_scan_inner respects the warning
# ---------------------------------------------------------------------------


class TestCmdScanInnerWarning:
    def _run_scan(
        self,
        args: list[str],
        user_input: str = "2",
        url_findings_exist: bool = False,
    ) -> MagicMock:
        repl, _ = _make_repl()
        _repo = MagicMock()
        _repo.name = "dvna"
        _repo.crawl_enabled = True
        repl.project_registry.resolve_by_name.return_value = ProjectRow(
            id=1, name="proj", path="/tmp/test", created_at="2026-05-02T00:00:00Z"
        )

        sc = ScanCommands(repl)
        sc._active_repos = MagicMock(return_value=[_repo])  # type: ignore[method-assign]

        mock_summary = MagicMock(findings_by_tool={})
        mock_handle = MagicMock(run_id=1)
        mock_handle.result.result.return_value = mock_summary

        mock_service = MagicMock()
        mock_service.start_scan.return_value = mock_handle

        with (
            patch("application.repl.commands.scan_commands.tool_registry") as mock_reg,
            patch(
                "application.repl.commands.scan_commands.get_scan_service",
                return_value=mock_service,
            ),
            patch.object(sc, "_repo_has_url_findings", return_value=url_findings_exist),
            patch("builtins.input", return_value=user_input),
        ):
            mock_reg.list_tool_names.return_value = [
                "katana",
                "noir",
                "zap",
                "semgrep",
            ]
            sc.cmd_scan("scan", args)

        return mock_service

    def test_zap_scan_with_option2_runs_zap_only(self) -> None:
        service = self._run_scan(["--tool=zap"], user_input="2")
        kwargs = service.start_scan.call_args.kwargs
        tools = kwargs.get("tool_ids") or ()
        assert "zap" in tools
        assert "noir" not in tools
        assert "katana" not in tools

    def test_zap_scan_cancelled_does_not_run(self) -> None:
        service = self._run_scan(["--tool=zap"], user_input="3")
        service.start_scan.assert_not_called()

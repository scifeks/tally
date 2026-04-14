"""Tests for the DAST-without-discovery warning in ScanCommands.

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


def _make_repl(repo_names: list[str] | None = None) -> MagicMock:
    repl = MagicMock()
    repl.active_project = "DVPA"
    repl.base_path = "/tmp/tally"
    names = repo_names if repo_names is not None else ["dvna"]
    repos = []
    for name in names:
        r = MagicMock()
        r.name = name
        r.node_app = False
        r.oas3_path = ""
        repos.append(r)
    repl.config.load_repositories.return_value = repos
    return repl


def _make_sc(repo_names: list[str] | None = None) -> ScanCommands:
    return ScanCommands(_make_repl(repo_names))


# ---------------------------------------------------------------------------
# _maybe_warn_dast_without_discovery helpers
# ---------------------------------------------------------------------------


class TestMaybeWarnDastWithoutDiscovery:
    def _call(
        self,
        tools: list[str],
        repo_name: str | None = None,
        auto_approve: bool = False,
        katana_oas3_exists: bool = False,
        noir_oas3_exists: bool = False,
        user_input: str = "1",
        repo_names: list[str] | None = None,
    ) -> list[str] | None:
        sc = _make_sc(repo_names)
        katana_result = "/tmp/dvna_katana_oas3.json" if katana_oas3_exists else None
        noir_result = "/tmp/dvna_noir_oas3.json" if noir_oas3_exists else None
        names: list[str] | None = [repo_name] if repo_name is not None else repo_names
        with (
            patch(
                "infrastructure.tools.wrappers.local.zap._find_katana_oas3",
                return_value=katana_result,
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
                return_value=noir_result,
            ),
            patch("builtins.input", return_value=user_input),
        ):
            return sc._maybe_warn_dast_without_discovery(
                tools, names, auto_approve, MagicMock()
            )

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

    def test_no_warning_when_katana_oas3_exists(self) -> None:
        result = self._call(["zap"], katana_oas3_exists=True)
        assert result == ["zap"]

    def test_no_warning_when_noir_oas3_exists(self) -> None:
        result = self._call(["zap"], noir_oas3_exists=True)
        assert result == ["zap"]

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
            patch(
                "infrastructure.tools.wrappers.local.zap._find_katana_oas3",
                return_value=None,
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
                return_value=None,
            ),
            patch("builtins.input", side_effect=EOFError),
        ):
            result = sc._maybe_warn_dast_without_discovery(
                ["zap"], None, False, MagicMock()
            )
        assert result is None

    def test_warning_printed_to_console(self) -> None:
        repl = _make_repl()
        sc = ScanCommands(repl)
        with (
            patch(
                "infrastructure.tools.wrappers.local.zap._find_katana_oas3",
                return_value=None,
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
                return_value=None,
            ),
            patch("builtins.input", return_value="2"),
        ):
            sc._maybe_warn_dast_without_discovery(["zap"], None, False, MagicMock())

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
        katana_oas3_exists: bool = False,
        noir_oas3_exists: bool = False,
    ) -> MagicMock:
        repl = _make_repl()
        _repo = MagicMock()
        _repo.name = "dvna"
        _repo.node_app = False
        _repo.oas3_path = ""
        repl.config.load_repositories.return_value = [_repo]

        sc = ScanCommands(repl)
        mock_orchestrator = MagicMock()
        katana_result = "/tmp/k_oas3.json" if katana_oas3_exists else None
        noir_result = "/tmp/n_oas3.json" if noir_oas3_exists else None

        with (
            patch("application.repl.commands.scan_commands.tool_registry") as mock_reg,
            patch.object(sc, "_make_orchestrator", return_value=mock_orchestrator),
            patch.object(
                sc, "_create_sqlite_run", return_value=(MagicMock(), MagicMock(), 1)
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_katana_oas3",
                return_value=katana_result,
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
                return_value=noir_result,
            ),
            patch("builtins.input", return_value=user_input),
        ):
            mock_reg.list_tool_names.return_value = [
                "katana",
                "noir",
                "zap",
                "semgrep",
            ]
            sc.cmd_scan("scan", args)

        return mock_orchestrator

    def test_zap_scan_with_option2_runs_zap_only(self) -> None:
        orchestrator = self._run_scan(["--tool=zap"], user_input="2")
        calls = [c.args[0] for c in orchestrator.run_tool_on_all_repos.call_args_list]
        assert "zap" in calls
        assert "noir" not in calls
        assert "katana" not in calls

    def test_zap_scan_cancelled_does_not_run(self) -> None:
        orchestrator = self._run_scan(["--tool=zap"], user_input="3")
        orchestrator.run_tool_on_all_repos.assert_not_called()
        orchestrator.run_full_scan.assert_not_called()

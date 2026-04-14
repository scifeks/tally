"""Tests for _maybe_warn_dast_without_discovery when oas3_path is set on repos.

Covers:
- When r.oas3_path is set, repo is NOT in the missing list (no warning)
- When r.oas3_path is empty and no discovery output, repo IS in the missing list
- Mixed repos: one with oas3_path, one without — only the second is missing
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.scan_commands import ScanCommands


def _make_repo(name: str, node_app: bool = False, oas3_path: str = "") -> MagicMock:
    r = MagicMock()
    r.name = name
    r.node_app = node_app
    r.oas3_path = oas3_path
    return r


def _make_sc(repos: list) -> ScanCommands:
    repl = MagicMock()
    repl.active_project = "DVPA"
    repl.base_path = "/tmp/tally"
    repl.config.load_repositories.return_value = repos
    return ScanCommands(repl)


class TestMaybeWarnDastWithoutDiscoveryOas3Path:
    def test_repo_with_oas3_path_not_in_missing(self) -> None:
        """oas3_path set — repo not in missing, warning not shown."""
        repo = _make_repo("api", oas3_path="/endpoints/api.json")
        sc = _make_sc([repo])
        mock_input = MagicMock()
        with (
            patch(
                "infrastructure.tools.wrappers.local.zap._find_katana_oas3",
                return_value=None,
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
                return_value=None,
            ),
            patch("builtins.input", mock_input),
        ):
            result = sc._maybe_warn_dast_without_discovery(
                ["zap"], None, False, MagicMock()
            )
        assert result == ["zap"]
        mock_input.assert_not_called()

    def test_repo_without_oas3_path_in_missing(self) -> None:
        """oas3_path empty and no discovery output — repo IS in missing."""
        repo = _make_repo("api", oas3_path="")
        sc = _make_sc([repo])
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
            result = sc._maybe_warn_dast_without_discovery(
                ["zap"], None, False, MagicMock()
            )
        # Warning shown; option 2 chosen — ZAP-only, tools unchanged
        assert result == ["zap"]

    def test_mixed_repos_only_missing_prompted(self) -> None:
        """One with oas3_path, one without — discovery prepended for latter."""
        repo_with = _make_repo("with-oas3", oas3_path="/api.json")
        repo_without = _make_repo("without-oas3", oas3_path="")
        sc = _make_sc([repo_with, repo_without])
        with (
            patch(
                "infrastructure.tools.wrappers.local.zap._find_katana_oas3",
                return_value=None,
            ),
            patch(
                "infrastructure.tools.wrappers.local.zap._find_noir_oas3",
                return_value=None,
            ),
            patch("builtins.input", return_value="1"),
        ):
            result = sc._maybe_warn_dast_without_discovery(
                ["zap"], None, False, MagicMock()
            )
        # Option 1 — katana prepended (and noir for non-node repos)
        assert result is not None
        assert "katana" in result
        assert "zap" in result

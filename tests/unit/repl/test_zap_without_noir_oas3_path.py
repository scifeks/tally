"""Tests for _maybe_warn_dast_without_discovery's URL-finding probe.

Phase 9: the warning no longer reads ``repo.oas3_path`` (that field is
gone); it queries the ``url_findings`` table via
``_repo_has_url_findings``. These tests stub that probe to drive the
warning path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.scan_commands import ScanCommands


def _make_repo(name: str, crawl_enabled: bool = True) -> MagicMock:
    r = MagicMock()
    r.name = name
    r.crawl_enabled = crawl_enabled
    return r


def _make_sc(repos: list) -> ScanCommands:
    repl = MagicMock()
    repl.active_project = "DVPA"
    repl.base_path = "/tmp/tally"
    sc = ScanCommands(repl)
    # _active_repos hits the per-project SQLite DB; stub at the instance.
    sc._active_repos = MagicMock(return_value=repos)  # type: ignore[method-assign]
    return sc


class TestMaybeWarnDastWithoutDiscoveryUrlFindings:
    def test_repo_with_url_findings_not_in_missing(self) -> None:
        """Repo has url_findings rows; no warning, tools unchanged."""
        repo = _make_repo("api")
        sc = _make_sc([repo])
        mock_input = MagicMock()
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=True),
            patch("builtins.input", mock_input),
        ):
            result = sc._maybe_warn_dast_without_discovery(["zap"], None, False, 1)
        assert result == ["zap"]
        mock_input.assert_not_called()

    def test_repo_without_url_findings_triggers_warning(self) -> None:
        """No url_findings rows; repo is in the missing list."""
        repo = _make_repo("api")
        sc = _make_sc([repo])
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=False),
            patch("builtins.input", return_value="2"),
        ):
            result = sc._maybe_warn_dast_without_discovery(["zap"], None, False, 1)
        # Warning shown; option 2 chosen; ZAP-only, tools unchanged
        assert result == ["zap"]

    def test_mixed_repos_only_missing_prompted(self) -> None:
        """One repo has url_findings, one doesn't; discovery prepended."""
        repo_with = _make_repo("with-urls")
        repo_without = _make_repo("without-urls")
        sc = _make_sc([repo_with, repo_without])

        def _has_findings(repo: object, _project_id: int) -> bool:
            return getattr(repo, "name", "") == "with-urls"

        with (
            patch.object(sc, "_repo_has_url_findings", side_effect=_has_findings),
            patch("builtins.input", return_value="1"),
        ):
            result = sc._maybe_warn_dast_without_discovery(["zap"], None, False, 1)
        # Option 1; katana prepended (and noir for non-node repos)
        assert result is not None
        assert "katana" in result
        assert "zap" in result

    def test_repo_with_crawl_disabled_not_in_missing(self) -> None:
        """crawl_enabled=False; repo excluded from missing, no warning."""
        repo = _make_repo("api", crawl_enabled=False)
        sc = _make_sc([repo])
        mock_input = MagicMock()
        with (
            patch.object(sc, "_repo_has_url_findings", return_value=False),
            patch("builtins.input", mock_input),
        ):
            result = sc._maybe_warn_dast_without_discovery(["zap"], None, False, 1)
        assert result == ["zap"]
        mock_input.assert_not_called()

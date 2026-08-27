"""Unit tests for the REPL burp scan command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.burp_commands import BurpCommands


def _make_repl(
    active_project: str | None = "testproject",
    base_urls: list[str] | None = None,
) -> tuple:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/test"
    repl.tool_registry = MagicMock()

    project_row = MagicMock()
    project_row.id = 1
    project_row.name = active_project
    repl.project_registry.resolve_by_name.return_value = project_row

    if base_urls is None:
        base_urls = ["https://target.example.com"]
    repo = MagicMock()
    svc = MagicMock()
    svc.base_urls = base_urls
    repo.services = [svc]
    repl.config = MagicMock()

    return repl, repo


class TestBurpScanCommand:
    def test_burp_scan_no_args_starts_scan(self):
        repl, repo = _make_repl()
        cmd = BurpCommands(repl)
        mock_handle = MagicMock()
        mock_handle.result.result.return_value = None

        mock_cfg = MagicMock()
        mock_cfg.global_config.burp = MagicMock()

        with (
            patch(
                "application.repl.commands.burp_commands.ProjectRepositoriesService"
            ) as mock_repo_svc,
            patch(
                "application.repl.commands.burp_commands.get_scan_service"
            ) as mock_svc,
            patch(
                "core.config.manager.ConfigManager",
                return_value=mock_cfg,
            ),
            patch(
                "application.repl.commands.burp_commands.create_scan_repos",
                return_value=(
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                ),
            ),
            patch(
                "application.repl.commands.burp_commands.create_finding_repo",
            ),
            patch(
                "application.repl.commands.burp_commands.create_repo_repo",
            ),
            patch(
                "application.repl.commands.burp_commands.create_url_finding_repo",
            ),
        ):
            mock_repo_svc.return_value.list_active.return_value = [repo]
            mock_svc.return_value.start_scan.return_value = mock_handle

            cmd.cmd_burp("burp", ["scan"])

        call_kw = mock_svc.return_value.start_scan.call_args.kwargs
        assert call_kw["burp_urls"] == ["https://target.example.com"]
        assert call_kw["burp_config_names"] is None

    def test_burp_scan_with_config_name(self):
        repl, repo = _make_repl()
        cmd = BurpCommands(repl)
        mock_handle = MagicMock()
        mock_handle.result.result.return_value = None

        mock_cfg = MagicMock()
        mock_cfg.global_config.burp = MagicMock()

        with (
            patch(
                "application.repl.commands.burp_commands.ProjectRepositoriesService"
            ) as mock_repo_svc,
            patch(
                "application.repl.commands.burp_commands.get_scan_service"
            ) as mock_svc,
            patch(
                "core.config.manager.ConfigManager",
                return_value=mock_cfg,
            ),
            patch(
                "application.repl.commands.burp_commands.create_scan_repos",
                return_value=(
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                ),
            ),
            patch(
                "application.repl.commands.burp_commands.create_finding_repo",
            ),
            patch(
                "application.repl.commands.burp_commands.create_repo_repo",
            ),
            patch(
                "application.repl.commands.burp_commands.create_url_finding_repo",
            ),
        ):
            mock_repo_svc.return_value.list_active.return_value = [repo]
            mock_svc.return_value.start_scan.return_value = mock_handle

            cmd.cmd_burp("burp", ["scan", "Crawl and Audit"])

        call_kw = mock_svc.return_value.start_scan.call_args.kwargs
        assert call_kw["burp_config_names"] == ["Crawl and Audit"]

    def test_burp_scan_no_active_project_prints_warning(
        self,
    ):
        repl, _ = _make_repl(active_project=None)
        cmd = BurpCommands(repl)
        cmd.cmd_burp("burp", ["scan"])
        repl.console.print.assert_called()

    def test_burp_scan_no_base_urls_prints_error(self):
        repl, repo = _make_repl(base_urls=[])
        cmd = BurpCommands(repl)

        with (
            patch(
                "application.repl.commands.burp_commands.ProjectRepositoriesService"
            ) as mock_repo_svc,
        ):
            mock_repo_svc.return_value.list_active.return_value = [repo]
            cmd.cmd_burp("burp", ["scan"])

        repl.console.print.assert_called()

    def test_burp_scan_not_configured_shows_error(self):
        repl, repo = _make_repl()
        cmd = BurpCommands(repl)

        mock_cfg = MagicMock()
        mock_cfg.global_config.burp = None

        with (
            patch(
                "application.repl.commands.burp_commands.ProjectRepositoriesService"
            ) as mock_repo_svc,
            patch(
                "core.config.manager.ConfigManager",
                return_value=mock_cfg,
            ),
        ):
            mock_repo_svc.return_value.list_active.return_value = [repo]
            cmd.cmd_burp("burp", ["scan"])

        repl.console.print.assert_called()
        call_args = repl.console.print.call_args[0][0]
        assert "Burp is not configured" in call_args

    def test_unknown_subcommand_shows_help(self):
        repl, _ = _make_repl()
        cmd = BurpCommands(repl)
        cmd.cmd_burp("burp", ["bogus"])
        repl.console.print.assert_called()

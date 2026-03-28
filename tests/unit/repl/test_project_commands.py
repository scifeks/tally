"""Unit tests for ProjectCommands."""

import unittest
from unittest.mock import MagicMock, patch

from application.repl.commands.project_commands import ProjectCommands


class TestProjectCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.repl = MagicMock()
        self.repl.console = MagicMock()
        self.repl.projects = MagicMock()
        self.repl.wizard = MagicMock()
        self.repl.active_project = "test-project"
        self.help_renderer = MagicMock()
        self.cmds = ProjectCommands(self.repl, self.help_renderer)

    # ------------------------------------------------------------------
    # cmd_project dispatch
    # ------------------------------------------------------------------

    def test_cmd_project_no_args_renders_help(self) -> None:
        self.cmds.cmd_project("project", [])
        self.help_renderer.render.assert_called_once_with("project")

    def test_cmd_project_add_calls_create_project(self) -> None:
        self.repl.wizard.create_project.return_value = "new-proj"
        self.cmds.cmd_project("project", ["add"])
        self.repl.wizard.create_project.assert_called_once()

    def test_cmd_project_switch_calls_switch_project(self) -> None:
        self.cmds.cmd_project("project", ["switch", "other"])
        self.repl.projects.switch_project.assert_called_once_with("other")

    def test_cmd_project_list_calls_list_projects(self) -> None:
        self.repl.projects.list_projects.return_value = []
        self.cmds.cmd_project("project", ["list"])
        self.repl.projects.list_projects.assert_called_once()

    def test_cmd_project_info_calls_get_project_info(self) -> None:
        info = MagicMock()
        info.created = "2026-01-01T00:00:00"
        info.repositories = []
        self.repl.projects.get_project_info.return_value = info
        self.cmds.cmd_project("project", ["info"])
        self.repl.projects.get_project_info.assert_called_once_with("test-project")

    def test_cmd_project_edit_calls_wizard_edit_project(self) -> None:
        self.cmds.cmd_project("project", ["edit", "some-proj"])
        self.repl.wizard.edit_project.assert_called_once_with("some-proj")

    def test_cmd_project_unknown_subcommand_prints_error(self) -> None:
        self.cmds.cmd_project("project", ["bogus"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Unknown subcommand", args[0])

    # ------------------------------------------------------------------
    # cmd_repo dispatch
    # ------------------------------------------------------------------

    def test_cmd_repo_no_args_renders_help(self) -> None:
        self.cmds.cmd_repo("repo", [])
        self.help_renderer.render.assert_called_once_with("repo")

    def test_cmd_repo_add_calls_add_repository(self) -> None:
        self.cmds.cmd_repo("repo", ["add"])
        self.repl.wizard.add_repository.assert_called_once_with("test-project")

    def test_cmd_repo_list_calls_load_repositories(self) -> None:
        self.repl.projects.config.load_repositories.return_value = []
        self.cmds.cmd_repo("repo", ["list"])
        self.repl.projects.config.load_repositories.assert_called_once_with(
            "test-project"
        )

    def test_cmd_repo_edit_calls_wizard_edit_repository(self) -> None:
        self.cmds.cmd_repo("repo", ["edit", "my-repo"])
        self.repl.wizard.edit_repository.assert_called_once_with(
            "test-project", "my-repo"
        )

    def test_cmd_repo_unknown_subcommand_prints_error(self) -> None:
        self.cmds.cmd_repo("repo", ["bogus"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Unknown subcommand", args[0])

    # ------------------------------------------------------------------
    # cmd_projects
    # ------------------------------------------------------------------

    def test_cmd_projects_no_projects_prints_warning(self) -> None:
        self.repl.projects.list_projects.return_value = []
        self.cmds.cmd_projects("projects", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("No projects found", args[0])

    def test_cmd_projects_with_projects_prints_table(self) -> None:
        self.repl.projects.list_projects.return_value = ["proj-a", "proj-b"]
        info = MagicMock()
        info.created = "2026-01-01T00:00:00"
        info.repositories = []
        self.repl.projects.get_project_info.return_value = info
        self.cmds.cmd_projects("projects", [])
        self.repl.console.print.assert_called_once()

    # ------------------------------------------------------------------
    # cmd_switch
    # ------------------------------------------------------------------

    def test_cmd_switch_no_args_prints_usage(self) -> None:
        self.cmds.cmd_switch("project", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Usage", args[0])

    def test_cmd_switch_success_sets_active_project(self) -> None:
        self.cmds.cmd_switch("project", ["other"])
        self.repl.projects.switch_project.assert_called_once_with("other")
        self.assertEqual(self.repl.active_project, "other")

    def test_cmd_switch_value_error_prints_not_found(self) -> None:
        self.repl.projects.switch_project.side_effect = ValueError("nope")
        self.cmds.cmd_switch("project", ["missing"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Project not found", args[0])

    # ------------------------------------------------------------------
    # cmd_new_project
    # ------------------------------------------------------------------

    def test_cmd_new_project_wizard_returns_name_sets_active(self) -> None:
        self.repl.wizard.create_project.return_value = "new-proj"
        self.cmds.cmd_new_project("project", [])
        self.assertEqual(self.repl.active_project, "new-proj")

    def test_cmd_new_project_wizard_returns_none_leaves_active(self) -> None:
        self.repl.wizard.create_project.return_value = None
        self.cmds.cmd_new_project("project", [])
        self.assertEqual(self.repl.active_project, "test-project")

    # ------------------------------------------------------------------
    # cmd_delete_project
    # ------------------------------------------------------------------

    def test_cmd_delete_project_no_args_prints_usage(self) -> None:
        self.cmds.cmd_delete_project("project", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Usage", args[0])

    def test_cmd_delete_project_confirmed_calls_delete(self) -> None:
        with patch("builtins.input", return_value="y"):
            self.cmds.cmd_delete_project("project", ["old-proj"])
        self.repl.projects.delete_project.assert_called_once_with("old-proj")

    def test_cmd_delete_project_declined_does_not_delete(self) -> None:
        with patch("builtins.input", return_value="n"):
            self.cmds.cmd_delete_project("project", ["old-proj"])
        self.repl.projects.delete_project.assert_not_called()
        args, _ = self.repl.console.print.call_args
        self.assertIn("Cancelled", args[0])

    def test_cmd_delete_project_value_error_prints_error(self) -> None:
        self.repl.projects.delete_project.side_effect = ValueError("err")
        with patch("builtins.input", return_value="y"):
            self.cmds.cmd_delete_project("project", ["old-proj"])
        self.repl.projects.delete_project.assert_called_once_with("old-proj")
        args, _ = self.repl.console.print.call_args
        self.assertIn("err", args[0])

    def test_cmd_delete_project_active_cleared_when_deleted(self) -> None:
        self.repl.active_project = "old-proj"
        with patch("builtins.input", return_value="y"):
            self.cmds.cmd_delete_project("project", ["old-proj"])
        self.assertIsNone(self.repl.active_project)

    # ------------------------------------------------------------------
    # cmd_edit_project
    # ------------------------------------------------------------------

    def test_cmd_edit_project_explicit_name_calls_wizard(self) -> None:
        self.cmds.cmd_edit_project("project", ["some-proj"])
        self.repl.wizard.edit_project.assert_called_once_with("some-proj")

    def test_cmd_edit_project_no_args_uses_active_project(self) -> None:
        self.repl.active_project = "active"
        self.cmds.cmd_edit_project("project", [])
        self.repl.wizard.edit_project.assert_called_once_with("active")

    def test_cmd_edit_project_no_args_no_active_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_edit_project("project", [])
        self.repl.wizard.edit_project.assert_not_called()
        self.repl.console.print.assert_called_once()

    def test_cmd_edit_project_value_error_prints_error(self) -> None:
        self.repl.wizard.edit_project.side_effect = ValueError("bad")
        self.cmds.cmd_edit_project("project", ["some-proj"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("bad", args[0])

    # ------------------------------------------------------------------
    # cmd_add_repo
    # ------------------------------------------------------------------

    def test_cmd_add_repo_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_add_repo("repo", [])
        self.repl.wizard.add_repository.assert_not_called()
        self.repl.console.print.assert_called_once()

    def test_cmd_add_repo_with_active_project_calls_wizard(self) -> None:
        self.cmds.cmd_add_repo("repo", [])
        self.repl.wizard.add_repository.assert_called_once_with("test-project")

    # ------------------------------------------------------------------
    # cmd_repos
    # ------------------------------------------------------------------

    def test_cmd_repos_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_repos("repo", [])
        self.repl.console.print.assert_called_once()

    def test_cmd_repos_empty_list_prints_no_repos_message(self) -> None:
        self.repl.projects.config.load_repositories.return_value = []
        self.cmds.cmd_repos("repo", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("No repositories configured", args[0])

    def test_cmd_repos_with_repos_prints_table(self) -> None:
        mock_repo = MagicMock()
        mock_repo.name = "r"
        mock_repo.type = ["web"]
        mock_repo.path = "/p"
        mock_repo.languages = ["python"]
        mock_repo.base_urls = ["http://x"]
        self.repl.projects.config.load_repositories.return_value = [mock_repo]
        self.cmds.cmd_repos("repo", [])
        self.repl.console.print.assert_called_once()

    # ------------------------------------------------------------------
    # cmd_edit_repo
    # ------------------------------------------------------------------

    def test_cmd_edit_repo_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_edit_repo("repo", ["my-repo"])
        self.repl.wizard.edit_repository.assert_not_called()
        self.repl.console.print.assert_called_once()

    def test_cmd_edit_repo_no_args_prints_usage(self) -> None:
        self.cmds.cmd_edit_repo("repo", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Usage", args[0])

    def test_cmd_edit_repo_calls_wizard(self) -> None:
        self.cmds.cmd_edit_repo("repo", ["my-repo"])
        self.repl.wizard.edit_repository.assert_called_once_with(
            "test-project", "my-repo"
        )

    def test_cmd_edit_repo_value_error_prints_error(self) -> None:
        self.repl.wizard.edit_repository.side_effect = ValueError("oops")
        self.cmds.cmd_edit_repo("repo", ["my-repo"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("oops", args[0])

    # ------------------------------------------------------------------
    # cmd_delete_repo
    # ------------------------------------------------------------------

    def test_cmd_delete_repo_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_delete_repo("repo", ["my-repo"])
        self.repl.projects.delete_repository.assert_not_called()
        self.repl.console.print.assert_called_once()

    def test_cmd_delete_repo_no_args_prints_usage(self) -> None:
        self.cmds.cmd_delete_repo("repo", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Usage", args[0])

    def test_cmd_delete_repo_confirmed_calls_delete(self) -> None:
        with patch("builtins.input", return_value="y"):
            self.cmds.cmd_delete_repo("repo", ["my-repo"])
        self.repl.projects.delete_repository.assert_called_once_with(
            "test-project", "my-repo"
        )

    def test_cmd_delete_repo_declined_does_not_delete(self) -> None:
        with patch("builtins.input", return_value="n"):
            self.cmds.cmd_delete_repo("repo", ["my-repo"])
        self.repl.projects.delete_repository.assert_not_called()
        args, _ = self.repl.console.print.call_args
        self.assertIn("Cancelled", args[0])

    def test_cmd_delete_repo_value_error_prints_error(self) -> None:
        self.repl.projects.delete_repository.side_effect = ValueError("gone")
        with patch("builtins.input", return_value="yes"):
            self.cmds.cmd_delete_repo("repo", ["my-repo"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("gone", args[0])

    # ------------------------------------------------------------------
    # cmd_project_info
    # ------------------------------------------------------------------

    def test_cmd_project_info_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_project_info("project", [])
        self.repl.console.print.assert_called_once()

    def test_cmd_project_info_none_result_prints_error(self) -> None:
        self.repl.projects.get_project_info.return_value = None
        self.cmds.cmd_project_info("project", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Could not load project", args[0])

    def test_cmd_project_info_success_prints_panel(self) -> None:
        mock_repo = MagicMock()
        mock_repo.name = "my-repo"
        mock_repo.languages = ["python"]
        info = MagicMock()
        info.created = "2026-01-01T00:00:00"
        info.repositories = [mock_repo]
        self.repl.projects.get_project_info.return_value = info
        self.cmds.cmd_project_info("project", [])
        self.repl.console.print.assert_called_once()

"""Unit tests for ProjectCommands."""

import unittest
from unittest.mock import MagicMock, patch

from application.repl.commands.project_commands import ProjectCommands
from domain.projects.entry import ProjectRow


class TestProjectCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.repl = MagicMock()
        self.repl.console = MagicMock()
        self.repl.projects = MagicMock()
        self.repl.project_registry = MagicMock()
        self.repl.wizard = MagicMock()
        self.repl.active_project = "test-project"
        self.help_renderer = MagicMock()
        self.cmds = ProjectCommands(self.repl, self.help_renderer)
        # Default repo lookup so _resolve_repo_arg("my-repo") finds the
        # repo for cmd_edit_repo / cmd_delete_repo tests.
        default_repo = MagicMock()
        default_repo.id = 1
        default_repo.name = "my-repo"
        self._active_repos_patcher = patch.object(
            ProjectCommands, "_active_repos", return_value=[default_repo]
        )
        self._active_repos_mock = self._active_repos_patcher.start()
        self.addCleanup(self._active_repos_patcher.stop)

    # cmd_project dispatch

    def test_cmd_project_unknown_subcommand_prints_error(self) -> None:
        self.cmds.cmd_project("project", ["bogus"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Unknown subcommand", args[0])

    # cmd_repo dispatch

    def test_cmd_repo_unknown_subcommand_prints_error(self) -> None:
        self.cmds.cmd_repo("repo", ["bogus"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Unknown subcommand", args[0])

    # cmd_projects

    def test_cmd_projects_no_projects_prints_warning(self) -> None:
        self.repl.project_registry.list_active.return_value = []
        self.cmds.cmd_projects("projects", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("No projects found", args[0])

    def test_cmd_projects_with_projects_prints_table(self) -> None:
        self.repl.project_registry.list_active.return_value = [
            ProjectRow(
                id=1,
                name="proj-a",
                path="/p/a",
                created_at="2026-01-01T00:00:00Z",
            ),
            ProjectRow(
                id=2,
                name="proj-b",
                path="/p/b",
                created_at="2026-01-01T00:00:00Z",
            ),
        ]
        info = MagicMock()
        info.created = "2026-01-01T00:00:00"
        info.repositories = []
        self.repl.projects.get_project_info.return_value = info
        self.cmds.cmd_projects("projects", [])
        self.repl.console.print.assert_called_once()

    # cmd_switch

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

    # cmd_new_project

    def test_cmd_new_project_wizard_returns_name_sets_active(self) -> None:
        self.repl.wizard.create_project.return_value = "new-proj"
        self.cmds.cmd_new_project("project", [])
        self.assertEqual(self.repl.active_project, "new-proj")

    def test_cmd_new_project_wizard_returns_none_leaves_active(self) -> None:
        self.repl.wizard.create_project.return_value = None
        self.cmds.cmd_new_project("project", [])
        self.assertEqual(self.repl.active_project, "test-project")

    # cmd_delete_project

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

    # cmd_edit_project

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

    # cmd_add_repo

    def test_cmd_add_repo_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_add_repo("repo", [])
        self.repl.wizard.add_repository.assert_not_called()
        self.repl.console.print.assert_called_once()

    # cmd_repos

    def test_cmd_repos_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_repos("repo", [])
        self.repl.console.print.assert_called_once()

    def test_cmd_repos_empty_list_prints_no_repos_message(self) -> None:
        self._active_repos_mock.return_value = []
        self.cmds.cmd_repos("repo", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("No repositories configured", args[0])

    def test_cmd_repos_with_repos_prints_table(self) -> None:
        mock_repo = MagicMock()
        mock_repo.name = "r"
        mock_repo.path = "/p"
        mock_repo.id = 1
        service = MagicMock()
        service.type = ["web"]
        service.languages = ["python"]
        service.base_urls = ["http://x"]
        service.docker_path = ""
        service.container_name = ""
        service.relative_path = ""
        service.dependencies_file = ""
        service.crawl_enabled = True
        service.test_dirs = []
        service.ignore_dirs = []
        mock_repo.services = [service]
        self._active_repos_mock.return_value = [mock_repo]
        self.cmds.cmd_repos("repo", [])
        self.repl.console.print.assert_called_once()

    # cmd_edit_repo

    def test_cmd_edit_repo_no_active_project_prints_warning(self) -> None:
        self.repl.active_project = None
        self.cmds.cmd_edit_repo("repo", ["my-repo"])
        self.repl.wizard.edit_repository.assert_not_called()
        self.repl.console.print.assert_called_once()

    def test_cmd_edit_repo_no_args_prints_usage(self) -> None:
        self.cmds.cmd_edit_repo("repo", [])
        args, _ = self.repl.console.print.call_args
        self.assertIn("Usage", args[0])

    def test_cmd_edit_repo_value_error_prints_error(self) -> None:
        self.repl.wizard.edit_repository.side_effect = ValueError("oops")
        self.cmds.cmd_edit_repo("repo", ["my-repo"])
        args, _ = self.repl.console.print.call_args
        self.assertIn("oops", args[0])

    # cmd_delete_repo

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

    # cmd_project_info

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
        service = MagicMock()
        service.languages = ["python"]
        service.docker_path = ""
        service.container_name = ""
        service.relative_path = ""
        service.dependencies_file = ""
        service.crawl_enabled = True
        service.type = []
        service.test_dirs = []
        service.ignore_dirs = []
        mock_repo.services = [service]
        info = MagicMock()
        info.created = "2026-01-01T00:00:00"
        info.repositories = [mock_repo]
        self.repl.projects.get_project_info.return_value = info
        self.cmds.cmd_project_info("project", [])
        self.repl.console.print.assert_called_once()

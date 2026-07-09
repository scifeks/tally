"""Unit tests for CLI project commands."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from application.cli.commands.project import (
    cmd_project_create,
    cmd_project_list,
)
from application.cli.exit_codes import GENERAL_ERROR, INVALID_ARGS, SUCCESS
from core.config.schemas.project_config import ProjectConfig
from domain.projects.entry import ProjectRow


class TestCmdProjectCreate:
    def test_creates_project_and_returns_json(self, capsys) -> None:
        """Project is created and JSON result is printed to stdout."""
        args = Namespace(
            project="test_project",
            company_name="ACME Corp",
            department_name="Security",
            abbreviation="AC",
        )
        registry = MagicMock()
        registry.resolve_by_name.side_effect = [
            None,
            ProjectRow(
                id=1,
                name="test_project",
                path="/path/to/project",
                created_at="2025-05-10T00:00:00Z",
                archived_at=None,
            ),
        ]

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            with patch("application.cli.commands.project.init_project_schema"):
                result = cmd_project_create(
                    args,
                    registry,
                    MagicMock(),
                    Path("/base"),
                )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["id"] == 1
        assert output["name"] == "test_project"

        mock_manager.create_project_dirs.assert_called_once_with("test_project")
        mock_manager.save_project.assert_called_once_with(
            "test_project",
            company_name="ACME Corp",
            department_name="Security",
            abbreviation="AC",
        )

    def test_returns_error_when_project_exists(self, capsys) -> None:
        """Returns GENERAL_ERROR when project already exists and is
        active."""
        args = Namespace(
            project="existing_project",
            company_name="",
            department_name="",
            abbreviation="",
        )
        existing_row = ProjectRow(
            id=2,
            name="existing_project",
            path="/path/to/project",
            created_at="2025-05-10T00:00:00Z",
            archived_at=None,
        )
        registry = MagicMock()
        registry.resolve_by_name.return_value = existing_row

        result = cmd_project_create(
            args,
            registry,
            MagicMock(),
            Path("/base"),
        )

        assert result == GENERAL_ERROR
        captured = capsys.readouterr()
        assert "already exists" in captured.err

    def test_returns_invalid_args_when_no_project_name(self, capsys) -> None:
        """Returns INVALID_ARGS when project name is missing."""
        args = Namespace(
            project=None,
            company_name="",
            department_name="",
            abbreviation="",
        )
        registry = MagicMock()

        result = cmd_project_create(
            args,
            registry,
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    def test_creates_with_default_optional_fields(self, capsys) -> None:
        """Optional fields default to empty strings when not provided."""
        args = Namespace(
            project="simple_project",
        )
        registry = MagicMock()
        registry.resolve_by_name.side_effect = [
            None,
            ProjectRow(
                id=3,
                name="simple_project",
                path="/path/to/project",
                created_at="2025-05-10T00:00:00Z",
                archived_at=None,
            ),
        ]

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            with patch("application.cli.commands.project.init_project_schema"):
                result = cmd_project_create(
                    args,
                    registry,
                    MagicMock(),
                    Path("/base"),
                )

        assert result == SUCCESS
        mock_manager.save_project.assert_called_once_with(
            "simple_project",
            company_name="",
            department_name="",
            abbreviation="",
        )

    def test_returns_error_when_project_manager_fails(self, capsys) -> None:
        """Returns GENERAL_ERROR when ProjectManager raises OSError."""
        args = Namespace(
            project="bad_project",
            company_name="",
            department_name="",
            abbreviation="",
        )
        registry = MagicMock()
        registry.resolve_by_name.return_value = None

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.create_project_dirs.side_effect = OSError("Permission denied")
            mock_manager_class.return_value = mock_manager

            result = cmd_project_create(
                args,
                registry,
                MagicMock(),
                Path("/base"),
            )

        assert result == GENERAL_ERROR
        captured = capsys.readouterr()
        assert "Permission denied" in captured.err

    def test_returns_error_when_cannot_resolve_created_project(self, capsys) -> None:
        """Returns GENERAL_ERROR if project cannot be re-resolved after
        creation."""
        args = Namespace(
            project="mystery_project",
            company_name="",
            department_name="",
            abbreviation="",
        )
        registry = MagicMock()
        registry.resolve_by_name.side_effect = [None, None]

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            with patch("application.cli.commands.project.init_project_schema"):
                result = cmd_project_create(
                    args,
                    registry,
                    MagicMock(),
                    Path("/base"),
                )

        assert result == GENERAL_ERROR
        captured = capsys.readouterr()
        assert "could not resolve" in captured.err


class TestCmdProjectList:
    def test_lists_projects_as_json(self, capsys) -> None:
        """Active projects are listed as JSON array with expected fields."""
        row1 = ProjectRow(
            id=1,
            name="project_alpha",
            path="/path/to/alpha",
            created_at="2025-05-10T00:00:00Z",
            archived_at=None,
        )
        row2 = ProjectRow(
            id=2,
            name="project_beta",
            path="/path/to/beta",
            created_at="2025-05-11T00:00:00Z",
            archived_at=None,
        )

        config1 = ProjectConfig(
            project_name="project_alpha",
            created="2025-05-10T12:00:00Z",
            abbreviation="PA",
        )
        config2 = ProjectConfig(
            project_name="project_beta",
            created="2025-05-11T12:00:00Z",
            abbreviation="PB",
        )

        registry = MagicMock()
        registry.list_active.return_value = [row1, row2]

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_project_info.side_effect = [config1, config2]
            mock_manager_class.return_value = mock_manager

            result = cmd_project_list(
                Namespace(),
                registry,
                MagicMock(),
                Path("/base"),
            )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) == 2
        assert output[0]["id"] == 1
        assert output[0]["name"] == "project_alpha"
        assert output[0]["code"] == "PA"
        assert output[0]["created_at"] == "2025-05-10T12:00:00Z"
        assert output[1]["id"] == 2
        assert output[1]["name"] == "project_beta"
        assert output[1]["code"] == "PB"

    def test_returns_empty_array_when_no_projects(self, capsys) -> None:
        """Empty JSON array is returned when there are no active projects."""
        registry = MagicMock()
        registry.list_active.return_value = []

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            result = cmd_project_list(
                Namespace(),
                registry,
                MagicMock(),
                Path("/base"),
            )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == []

    def test_skips_projects_with_no_config(self, capsys) -> None:
        """Projects without config are skipped in the output."""
        row1 = ProjectRow(
            id=1,
            name="project_one",
            path="/path/to/one",
            created_at="2025-05-10T00:00:00Z",
            archived_at=None,
        )
        row2 = ProjectRow(
            id=2,
            name="project_two",
            path="/path/to/two",
            created_at="2025-05-11T00:00:00Z",
            archived_at=None,
        )

        config1 = ProjectConfig(
            project_name="project_one",
            created="2025-05-10T12:00:00Z",
            abbreviation="P1",
        )

        registry = MagicMock()
        registry.list_active.return_value = [row1, row2]

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_project_info.side_effect = [config1, None]
            mock_manager_class.return_value = mock_manager

            result = cmd_project_list(
                Namespace(),
                registry,
                MagicMock(),
                Path("/base"),
            )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) == 1
        assert output[0]["name"] == "project_one"

    def test_includes_optional_fields(self, capsys) -> None:
        """Optional config fields are included in the output."""
        row = ProjectRow(
            id=1,
            name="full_project",
            path="/path/to/project",
            created_at="2025-05-10T00:00:00Z",
            archived_at=None,
        )

        config = ProjectConfig(
            project_name="full_project",
            created="2025-05-10T12:00:00Z",
            company_name="Acme",
            department_name="Security",
            abbreviation="FM",
        )

        registry = MagicMock()
        registry.list_active.return_value = [row]

        with patch(
            "application.cli.commands.project.ProjectManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_project_info.return_value = config
            mock_manager_class.return_value = mock_manager

            result = cmd_project_list(
                Namespace(),
                registry,
                MagicMock(),
                Path("/base"),
            )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output[0]["code"] == "FM"
        assert output[0]["created_at"] == "2025-05-10T12:00:00Z"

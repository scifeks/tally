"""Unit tests for the finding-update CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.cli.commands.finding import cmd_finding_update
from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError
from application.mcp.finding_payload import FindingPayloadError

_MODULE = "application.cli.commands.finding"


def _args(
    finding_id: int | None = 1,
    status: str | None = None,
    description: str | None = None,
    project: str | None = "myapp",
) -> MagicMock:
    args = MagicMock()
    args.project = project
    args.finding_id = finding_id
    args.status = status
    args.description = description
    return args


class TestCmdFindingUpdate:
    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_updates_status_and_prints_id(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        service = mock_factory.return_value
        service.update_finding_fields.return_value = True

        code = cmd_finding_update(
            _args(finding_id=42, status="fixed"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == SUCCESS
        out = capsys.readouterr().out
        assert '"finding_id": 42' in out
        service.update_finding_fields.assert_called_once_with(
            42, status="fixed", description=None
        )

    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_updates_description(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        service = mock_factory.return_value
        service.update_finding_fields.return_value = True

        code = cmd_finding_update(
            _args(description="new text"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == SUCCESS
        service.update_finding_fields.assert_called_once_with(
            1, status=None, description="new text"
        )

    def test_no_fields_is_invalid_args(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = cmd_finding_update(
            _args(status=None, description=None),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == INVALID_ARGS
        assert "at least one" in capsys.readouterr().err.lower()

    def test_missing_finding_id_is_invalid_args(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = cmd_finding_update(
            _args(finding_id=None, status="fixed"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == INVALID_ARGS

    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_finding_not_found_is_general_error(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        mock_factory.return_value.update_finding_fields.return_value = False

        code = cmd_finding_update(
            _args(finding_id=999, status="fixed"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == GENERAL_ERROR
        assert "not found" in capsys.readouterr().err.lower()

    @patch(f"{_MODULE}.resolve_project")
    def test_unknown_project_is_project_not_found(
        self, mock_resolve: MagicMock
    ) -> None:
        mock_resolve.side_effect = ProjectResolutionError("no such project")

        code = cmd_finding_update(
            _args(status="fixed"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == PROJECT_NOT_FOUND

    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_invalid_status_is_invalid_args(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        mock_factory.return_value.update_finding_fields.side_effect = (
            FindingPayloadError("status 'bogus' is invalid")
        )

        code = cmd_finding_update(
            _args(status="bogus"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == INVALID_ARGS
        assert "bogus" in capsys.readouterr().err

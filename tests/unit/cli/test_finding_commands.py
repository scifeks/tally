"""Unit tests for the finding-add CLI command."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.cli.commands.finding import cmd_finding_add
from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError
from application.mcp.finding_payload import FindingPayloadError
from application.mcp.ingest_service import UnknownRepositoryError

_MODULE = "application.cli.commands.finding"


def _args(
    finding_file: str | None,
    repo: str | None = "api",
    status: str = "active",
    project: str | None = "myapp",
) -> MagicMock:
    args = MagicMock()
    args.project = project
    args.repo = repo
    args.finding_file = finding_file
    args.status = status
    return args


@pytest.fixture()
def payload_file(tmp_path: Path) -> Path:
    path = tmp_path / "payload.json"
    path.write_text(json.dumps({"description": "x"}))
    return path


class TestCmdFindingAdd:
    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_records_finding_from_file_and_prints_id(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        payload_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        service = mock_factory.return_value
        service.record_manual_finding.return_value = 42

        code = cmd_finding_add(
            _args(str(payload_file), status="false_positive"),
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert code == SUCCESS
        assert json.loads(capsys.readouterr().out) == {"finding_id": 42}
        service.record_manual_finding.assert_called_once_with(
            {"description": "x"}, repo_name="api", status="false_positive"
        )

    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_reads_payload_from_stdin_when_dash(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        service = mock_factory.return_value
        service.record_manual_finding.return_value = 7
        monkeypatch.setattr("sys.stdin", io.StringIO('{"description": "y"}'))

        code = cmd_finding_add(_args("-"), MagicMock(), MagicMock(), Path("/base"))

        assert code == SUCCESS
        assert service.record_manual_finding.call_args.args[0] == {"description": "y"}

    @pytest.mark.parametrize(
        ("contents", "missing"),
        [
            (None, True),
            ("{not json", False),
            ("[1, 2]", False),
        ],
        ids=["missing-file", "invalid-json", "not-an-object"],
    )
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_unusable_payload_file_is_invalid_args(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        tmp_path: Path,
        contents: str | None,
        missing: bool,
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        path = tmp_path / "payload.json"
        if not missing and contents is not None:
            path.write_text(contents)

        code = cmd_finding_add(
            _args(str(path)), MagicMock(), MagicMock(), Path("/base")
        )

        assert code == INVALID_ARGS
        mock_factory.return_value.record_manual_finding.assert_not_called()

    @pytest.mark.parametrize(
        ("error", "expected_code"),
        [
            (FindingPayloadError("status 'fp' is invalid"), INVALID_ARGS),
            (UnknownRepositoryError("repository 'api' is not active"), INVALID_ARGS),
            (RuntimeError("disk full"), GENERAL_ERROR),
        ],
        ids=["invalid-payload-or-status", "unknown-repo", "unexpected"],
    )
    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_service_errors_map_to_exit_codes_with_message(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        payload_file: Path,
        capsys: pytest.CaptureFixture[str],
        error: Exception,
        expected_code: int,
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        mock_factory.return_value.record_manual_finding.side_effect = error

        code = cmd_finding_add(
            _args(str(payload_file)), MagicMock(), MagicMock(), Path("/base")
        )

        assert code == expected_code
        captured = capsys.readouterr()
        assert str(error) in captured.err
        assert captured.out == ""

    @patch(f"{_MODULE}.ProjectPaths")
    @patch(f"{_MODULE}.create_ingest_service")
    @patch(f"{_MODULE}.resolve_project")
    def test_service_construction_failure_is_general_error(
        self,
        mock_resolve: MagicMock,
        mock_factory: MagicMock,
        mock_paths: MagicMock,
        payload_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_resolve.return_value = (1, MagicMock())
        mock_factory.side_effect = RuntimeError("db init failed")

        code = cmd_finding_add(
            _args(str(payload_file)), MagicMock(), MagicMock(), Path("/base")
        )

        assert code == GENERAL_ERROR
        assert "db init failed" in capsys.readouterr().err

    @patch(f"{_MODULE}.resolve_project")
    def test_unknown_project_is_project_not_found(
        self, mock_resolve: MagicMock, payload_file: Path
    ) -> None:
        mock_resolve.side_effect = ProjectResolutionError("no such project")

        code = cmd_finding_add(
            _args(str(payload_file)), MagicMock(), MagicMock(), Path("/base")
        )

        assert code == PROJECT_NOT_FOUND

    @pytest.mark.parametrize(
        ("repo", "finding_file"),
        [(None, "payload.json"), ("api", None)],
        ids=["no-repo", "no-finding-file"],
    )
    def test_missing_required_flag_is_invalid_args(
        self, repo: str | None, finding_file: str | None
    ) -> None:
        code = cmd_finding_add(
            _args(finding_file, repo=repo), MagicMock(), MagicMock(), Path("/base")
        )

        assert code == INVALID_ARGS

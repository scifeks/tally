"""Unit tests for IngestHandler repo_id resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.handlers import IngestHandler
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult


def _make_event(
    tool_name: str = "dalfox",
    repo: str = "dveca",
    run_id: int = 1,
) -> ToolCompleted:
    result = MagicMock(spec=ToolResult)
    result.tool_name = tool_name
    result.success = True
    result.parsed_data = {"findings": []}
    return ToolCompleted(
        result=result,
        profile="dveca",
        run_id=run_id,
        project_name="test",
        base_path="/tmp",
        repo=repo,
    )


class TestIngestHandlerRepoId:
    def test_web_tool_gets_repo_id(self) -> None:
        bus = MagicMock()
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        repo_repo.find_id_by_name.return_value = 42

        handler = IngestHandler(bus, finding_repo, repo_repo)

        mock_tool_handler = MagicMock()
        mock_tool_handler.domain = "web"
        mock_tool_handler.segment = "web"
        mock_tool_handler.normalize.return_value = [
            {"tool": "dalfox", "url": "http://127.0.0.1/test"}
        ]

        with patch(
            "application.pipeline.handlers.ToolHandlerFactory.load",
            return_value=mock_tool_handler,
        ):
            handler.handle(_make_event(tool_name="dalfox", repo="dveca"))

        call_args = finding_repo.insert_findings.call_args
        rows = call_args[0][1]
        assert rows[0]["repo_id"] == 42
        assert rows[0]["repo"] == "dveca"

    def test_sca_tool_gets_repo_id(self) -> None:
        bus = MagicMock()
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        repo_repo.find_id_by_name.return_value = 7

        handler = IngestHandler(bus, finding_repo, repo_repo)

        mock_tool_handler = MagicMock()
        mock_tool_handler.domain = "code"
        mock_tool_handler.segment = "sca"
        mock_tool_handler.normalize.return_value = [
            {"tool": "osv-scanner", "package": "lodash"}
        ]

        with patch(
            "application.pipeline.handlers.ToolHandlerFactory.load",
            return_value=mock_tool_handler,
        ):
            handler.handle(_make_event(tool_name="osv-scanner", repo="dveca"))

        call_args = finding_repo.insert_findings.call_args
        rows = call_args[0][1]
        assert rows[0]["repo_id"] == 7
        assert rows[0]["repo"] == "dveca"

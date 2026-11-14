"""Burp scan flow stamps repo_id on findings."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.handlers import IngestHandler
from domain.findings.normalization import NormalizedFinding
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult


def _make_burp_event(repo: str = "", run_id: int = 1) -> ToolCompleted:
    result = MagicMock(spec=ToolResult)
    result.tool_name = "burp"
    result.success = True
    result.parsed_data = {"findings": []}
    return ToolCompleted(
        result=result,
        profile="",
        run_id=run_id,
        project_name="test",
        base_path="/tmp",
        repo=repo,
    )


def _mock_repo(name: str, repo_id: int, base_urls: list[str]) -> MagicMock:
    svc = MagicMock()
    svc.base_urls = base_urls
    repo = MagicMock()
    repo.name = name
    repo.id = repo_id
    repo.services = [svc]
    return repo


class TestBurpScanRepoResolution:
    def test_burp_finding_gets_repo_id_via_url(self) -> None:
        bus = MagicMock()
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        repo_repo.find_id_by_name.return_value = 5
        repo_repo.list_active.return_value = [
            _mock_repo("webgoat", 5, ["http://127.0.0.1:8081"])
        ]

        handler = IngestHandler(bus, finding_repo, repo_repo)

        mock_tool_handler = MagicMock()
        mock_tool_handler.domain = "web"
        mock_tool_handler.segment = "web"
        mock_tool_handler.normalize.return_value = [
            {
                "tool": "burp",
                "url": "http://127.0.0.1:8081/WebGoat/login",
            }
        ]
        mock_tool_handler.fingerprint_key.return_value = "burp|test"

        with patch(
            "application.pipeline.handlers.ToolHandlerFactory.load",
            return_value=mock_tool_handler,
        ):
            handler.handle(_make_burp_event(repo=""))

        call_args = finding_repo.insert_findings.call_args
        rows = call_args[0][1]
        assert isinstance(rows[0], NormalizedFinding)
        assert rows[0].columns.get("repo_id") == 5

    def test_burp_finding_no_match_stays_unlinked(self) -> None:
        bus = MagicMock()
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [
            _mock_repo("other", 3, ["http://10.0.0.1:9090"])
        ]

        handler = IngestHandler(bus, finding_repo, repo_repo)

        mock_tool_handler = MagicMock()
        mock_tool_handler.domain = "web"
        mock_tool_handler.segment = "web"
        mock_tool_handler.normalize.return_value = [
            {
                "tool": "burp",
                "url": "http://unknown:1234/foo",
            }
        ]
        mock_tool_handler.fingerprint_key.return_value = "burp|test"

        with patch(
            "application.pipeline.handlers.ToolHandlerFactory.load",
            return_value=mock_tool_handler,
        ):
            handler.handle(_make_burp_event(repo=""))

        call_args = finding_repo.insert_findings.call_args
        rows = call_args[0][1]
        assert rows[0].columns.get("repo_id") is None

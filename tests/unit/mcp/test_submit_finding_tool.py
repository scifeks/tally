"""Unit tests for the submit_finding MCP tool wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from mcp_server.server import create_mcp_server


def test_tool_passes_project_repo_store_and_repo_id(tmp_path: Path) -> None:
    row = MagicMock()
    row.archived_at = None
    registry = MagicMock()
    registry.resolve_by_name.return_value = row
    repo_store = MagicMock()
    finding: dict[str, Any] = {"file": "a.py"}

    with (
        patch("mcp_server.server.ConfigManager"),
        patch("mcp_server.server.ProjectPaths"),
        patch("mcp_server.server.ConnectionFactory"),
        patch("mcp_server.server.FindingRepository"),
        patch("mcp_server.server.RunRepository"),
        patch("mcp_server.server.FindingIndexer"),
        patch("mcp_server.server.get_or_build_knowledge_base"),
        patch("mcp_server.server.RepositoryRepository", return_value=repo_store),
        patch("mcp_server.server.McpIngestService") as service_cls,
    ):
        server = create_mcp_server(registry, MagicMock(), tmp_path)
        tool = server._tool_manager._tools["submit_finding"].fn
        tool("myproject", 1, 7, 3, finding)

    assert service_cls.call_args.kwargs["repo_repo"] is repo_store
    service_cls.return_value.submit_finding.assert_called_once_with(
        3, finding, repo_id=7
    )

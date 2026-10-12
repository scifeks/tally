"""Unit tests for the ingest_attack_surface MCP tool."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.server import create_mcp_server

SPEC = """\
openapi: 3.1.0
info: {title: t, version: "1"}
paths:
  /a:
    get:
      responses: {"200": {description: ok}}
"""


def _server(tmp_path: Path, registry: MagicMock) -> Any:
    with patch("mcp_server.server.ConfigManager"):
        return create_mcp_server(registry, MagicMock(), tmp_path)


def _tool(tmp_path: Path, registry: MagicMock) -> Any:
    server = _server(tmp_path, registry)
    return server._tool_manager._tools["ingest_attack_surface"].fn


@pytest.fixture
def registry(tmp_path: Path) -> MagicMock:
    row = MagicMock()
    row.name = "myproject"
    row.archived_at = None
    reg = MagicMock()
    reg.resolve_by_name.return_value = row
    return reg


@pytest.fixture
def fake_paths(tmp_path: Path) -> MagicMock:
    paths = MagicMock()
    paths.findings_db = tmp_path / "findings.db"
    paths.endpoint_dir.return_value = tmp_path / "endpoints" / "7"
    return paths


def test_tool_is_registered(tmp_path: Path, registry: MagicMock) -> None:
    server = _server(tmp_path, registry)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "ingest_attack_surface" in names


def test_happy_path_delegates_and_counts(
    tmp_path: Path, registry: MagicMock, fake_paths: MagicMock
) -> None:
    spec = tmp_path / "attack-surface.yaml"
    spec.write_text(SPEC)
    merged = tmp_path / "endpoints" / "7"
    merged.mkdir(parents=True)
    (merged / "merged_urls.txt").write_text("http://x/a\nhttp://x/b\n\n")

    repo_store = MagicMock()
    repo_store.get_by_name.return_value = MagicMock()
    repo_store.find_id_by_name.return_value = 7
    with (
        patch("mcp_server.server.ProjectPaths") as paths_cls,
        patch("mcp_server.server.ConnectionFactory"),
        patch("mcp_server.server.UrlFindingRepository"),
        patch("mcp_server.server.UrlInventoryService"),
        patch("mcp_server.server.EndpointFileConverter"),
        patch("mcp_server.server.RepositoryRepository", return_value=repo_store),
        patch("mcp_server.server.UrlListService") as svc_cls,
    ):
        paths_cls.from_registry_row.return_value = fake_paths
        result = _tool(tmp_path, registry)("myproject", "myrepo", str(spec))

    assert result == {"status": "ok", "endpoints_ingested": 2}
    kwargs = svc_cls.return_value.ingest_uploaded_endpoint_file.call_args.kwargs
    assert kwargs["repo_id"] == 7
    assert kwargs["filename"] == "attack-surface.yaml"
    assert kwargs["contents"] == SPEC.encode()


def test_missing_file_returns_error(tmp_path: Path, registry: MagicMock) -> None:
    result = _tool(tmp_path, registry)("myproject", "myrepo", "/no/such/file.yaml")
    assert result["status"] == "error"
    assert "not found" in result["error"].lower()


def test_unknown_project_returns_error(tmp_path: Path) -> None:
    reg = MagicMock()
    reg.resolve_by_name.return_value = None
    result = _tool(tmp_path, reg)("nosuchproject", "repo", str(tmp_path / "x.yaml"))
    assert result["status"] == "error"
    assert "not found" in result["error"].lower()


def test_unknown_repo_returns_error(
    tmp_path: Path, registry: MagicMock, fake_paths: MagicMock
) -> None:
    spec = tmp_path / "s.yaml"
    spec.write_text(SPEC)
    repo_store = MagicMock()
    repo_store.get_by_name.return_value = None
    repo_store.find_id_by_name.return_value = None
    with (
        patch("mcp_server.server.ProjectPaths") as paths_cls,
        patch("mcp_server.server.ConnectionFactory"),
        patch("mcp_server.server.UrlFindingRepository"),
        patch("mcp_server.server.RepositoryRepository", return_value=repo_store),
    ):
        paths_cls.from_registry_row.return_value = fake_paths
        result = _tool(tmp_path, registry)("myproject", "ghost", str(spec))
    assert result["status"] == "error"
    assert "ghost" in result["error"]

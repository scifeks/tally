"""Unit tests for filesystem browse API endpoint."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api.global_settings import router


@pytest.fixture()
def browse_dir(tmp_path):
    (tmp_path / "common.txt").write_text("test")
    (tmp_path / "api-list.txt").write_text("test")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("test")
    return tmp_path


@pytest.fixture()
def client(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "global.json").write_text(json.dumps({}))
    app = FastAPI()
    app.state.base_path = str(tmp_path)
    app.include_router(router, prefix="/api/v1/global-settings")
    return TestClient(app)


class TestBrowseFilesystem:
    def test_lists_directory_contents(self, client, browse_dir):
        resp = client.get(
            "/api/v1/global-settings/fs-browse",
            params={"path": str(browse_dir)},
        )
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()["entries"]]
        assert "common.txt" in names
        assert "subdir" in names

    def test_marks_directories(self, client, browse_dir):
        resp = client.get(
            "/api/v1/global-settings/fs-browse",
            params={"path": str(browse_dir)},
        )
        entries = resp.json()["entries"]
        subdir = next(e for e in entries if e["name"] == "subdir")
        assert subdir["isDir"] is True

    def test_rejects_nonexistent_path(self, client):
        resp = client.get(
            "/api/v1/global-settings/fs-browse",
            params={"path": "/nonexistent/path/xyz"},
        )
        assert resp.status_code == 400

    def test_rejects_relative_path(self, client):
        resp = client.get(
            "/api/v1/global-settings/fs-browse",
            params={"path": "../etc"},
        )
        assert resp.status_code == 400

    def test_returns_current_path(self, client, browse_dir):
        resp = client.get(
            "/api/v1/global-settings/fs-browse",
            params={"path": str(browse_dir)},
        )
        assert resp.json()["currentPath"] == str(browse_dir)

    def test_sorts_dirs_first_then_files(self, client, browse_dir):
        resp = client.get(
            "/api/v1/global-settings/fs-browse",
            params={"path": str(browse_dir)},
        )
        entries = resp.json()["entries"]
        dir_indices = [i for i, e in enumerate(entries) if e["isDir"]]
        file_indices = [i for i, e in enumerate(entries) if not e["isDir"]]
        if dir_indices and file_indices:
            assert max(dir_indices) < min(file_indices)

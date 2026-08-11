"""Unit tests for global settings API endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api.global_settings import router


@pytest.fixture()
def client(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "global.json").write_text("{}")
    app = FastAPI()
    app.state.base_path = str(tmp_path)
    app.include_router(router, prefix="/api/v1/global-settings")
    return TestClient(app)


class TestFilesystemBrowse:
    def test_browse_root_directory(self, client):
        resp = client.get("/api/v1/global-settings/fs-browse?path=/tmp")
        assert resp.status_code == 200
        data = resp.json()
        assert "currentPath" in data
        assert "entries" in data

    def test_invalid_path_returns_400(self, client):
        resp = client.get("/api/v1/global-settings/fs-browse?path=relative/path")
        assert resp.status_code == 400

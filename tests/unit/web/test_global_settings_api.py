"""Unit tests for global settings API endpoints."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api.global_settings import router


@pytest.fixture()
def config_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "global.json").write_text(
        json.dumps({"ffuf_wordlist_paths": ["/usr/share/seclists/common.txt"]})
    )
    return tmp_path


@pytest.fixture()
def client(config_dir):
    app = FastAPI()
    app.state.base_path = str(config_dir)
    app.include_router(router, prefix="/api/v1/global-settings")
    return TestClient(app)


class TestGetToolSettings:
    def test_returns_wordlist_paths(self, client):
        resp = client.get("/api/v1/global-settings/tool-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ffufWordlistPaths"] == ["/usr/share/seclists/common.txt"]

    def test_returns_empty_list_when_no_paths(self, tmp_path):
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "global.json").write_text(json.dumps({"ffuf_wordlist_paths": []}))
        app = FastAPI()
        app.state.base_path = str(tmp_path)
        app.include_router(router, prefix="/api/v1/global-settings")
        c = TestClient(app)
        resp = c.get("/api/v1/global-settings/tool-config")
        assert resp.json()["ffufWordlistPaths"] == []


class TestUpdateToolSettings:
    def test_updates_wordlist_paths(self, client, config_dir):
        resp = client.put(
            "/api/v1/global-settings/tool-config",
            json={"ffufWordlistPaths": ["/new/a.txt", "/new/b.txt"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ffufWordlistPaths"] == [
            "/new/a.txt",
            "/new/b.txt",
        ]
        saved = json.loads((config_dir / "config" / "global.json").read_text())
        assert saved["ffuf_wordlist_paths"] == [
            "/new/a.txt",
            "/new/b.txt",
        ]

"""Integration tests for GET /api/v1/capabilities."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from infrastructure.store.connection import ConnectionFactory
from tests._app_factory import build_test_app
from tests.integration.web.conftest import HANDSHAKE, TEST_PORT

pytestmark = pytest.mark.integration


def _make_unauthed_app(tmp_path: Path):
    db_path = tmp_path / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ConnectionFactory(db_path).init_schema()
    return build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)


class TestCapabilities:
    async def test_returns_expected_fields(self, app_client) -> None:
        client, *_ = app_client
        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "chat_enabled",
            "triage_enabled",
            "report_retention_enabled",
            "max_report_history",
            "triage_backend_label",
            "triage_mode",
        }

    async def test_field_types(self, app_client) -> None:
        client, *_ = app_client
        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["chat_enabled"], bool)
        assert isinstance(data["triage_enabled"], bool)
        assert isinstance(data["report_retention_enabled"], bool)
        assert isinstance(data["max_report_history"], int)
        assert (
            isinstance(data["triage_backend_label"], str)
            or data["triage_backend_label"] is None
        )
        assert isinstance(data["triage_mode"], str) or data["triage_mode"] is None

    async def test_report_retention_enabled_is_false(self, app_client) -> None:
        """Hardcoded False until a retention sweep mechanism exists."""
        client, *_ = app_client
        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        assert resp.json()["report_retention_enabled"] is False

    async def test_max_report_history_default(self, app_client) -> None:
        """Defaults to GlobalConfig.report_retention_count (10)."""
        client, *_ = app_client
        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        assert resp.json()["max_report_history"] == 10

    async def test_chat_enabled_false_when_no_config(self, tmp_path: Path) -> None:
        """When config/global.json is missing, capabilities falls back to
        chat_enabled=False (FileNotFoundError swallowed inside the service)."""
        db_path = tmp_path / "projects" / "p1" / "sqlite" / "findings.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ConnectionFactory(db_path).init_schema()
        app = build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            exch = await client.post(
                "/api/v1/auth/exchange",
                json={"token": HANDSHAKE},
                headers={"origin": f"https://127.0.0.1:{TEST_PORT}"},
            )
            assert exch.status_code == 200
            for name, value in exch.cookies.items():
                client.cookies.delete(name, domain="127.0.0.1")
                client.cookies.set(name, value)
            resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        assert resp.json()["chat_enabled"] is False

    async def test_chat_enabled_true_when_provider_is_ollama(
        self, tmp_path: Path
    ) -> None:
        """When chat_inference is configured, chat_enabled is True."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "global.json").write_text(
            '{"chat_inference": {"provider": "ollama"}}'
        )
        db_path = tmp_path / "projects" / "p1" / "sqlite" / "findings.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ConnectionFactory(db_path).init_schema()
        app = build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            exch = await client.post(
                "/api/v1/auth/exchange",
                json={"token": HANDSHAKE},
                headers={"origin": f"https://127.0.0.1:{TEST_PORT}"},
            )
            assert exch.status_code == 200
            for name, value in exch.cookies.items():
                client.cookies.delete(name, domain="127.0.0.1")
                client.cookies.set(name, value)
            resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        assert resp.json()["chat_enabled"] is True

    async def test_chat_enabled_false_when_no_chat_inference(
        self, tmp_path: Path
    ) -> None:
        """Missing chat_inference yields chat_enabled=False."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "global.json").write_text("{}")
        db_path = tmp_path / "projects" / "p1" / "sqlite" / "findings.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ConnectionFactory(db_path).init_schema()
        app = build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            exch = await client.post(
                "/api/v1/auth/exchange",
                json={"token": HANDSHAKE},
                headers={"origin": f"https://127.0.0.1:{TEST_PORT}"},
            )
            assert exch.status_code == 200
            for name, value in exch.cookies.items():
                client.cookies.delete(name, domain="127.0.0.1")
                client.cookies.set(name, value)
            resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        assert resp.json()["chat_enabled"] is False

    async def test_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/capabilities")
        assert resp.status_code in (401, 403)

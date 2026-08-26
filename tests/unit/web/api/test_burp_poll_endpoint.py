"""Unit tests for Burp Organizer poll endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api._errors import install_error_handlers
from web.api.burp_poll import v1_router


def _make_app(
    *,
    burp_mcp_url: str = "http://127.0.0.1:9876/sse",
    poll_interval: int = 30,
) -> tuple[FastAPI, MagicMock]:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(v1_router, prefix="/api/v1/projects")

    burp_cfg = MagicMock()
    burp_cfg.mcp_url = burp_mcp_url
    burp_cfg.poll_interval_seconds = poll_interval

    global_cfg = MagicMock()
    global_cfg.burp = burp_cfg if burp_mcp_url else None

    cfg_manager = MagicMock()
    cfg_manager.global_config = global_cfg

    app.state.base_path = "/tmp/tally_test"
    app.state.project_registry = MagicMock()
    return app, cfg_manager


def _project_row(project_id: int = 1):
    row = MagicMock()
    row.id = project_id
    row.name = "testproj"
    row.path = "/tmp/tally_test/projects/testproj"
    row.archived_at = None
    return row


class TestStartPoll:
    @patch("web.api.burp_poll.threading.Thread")
    @patch("web.api.burp_poll.OrganizerPoller")
    @patch("web.api.burp_poll.BurpMcpClient")
    @patch("web.api.burp_poll.OrganizerStateRepository")
    @patch("web.api.burp_poll.McpIngestService")
    @patch("web.api.burp_poll.create_finding_repo")
    @patch("web.api.burp_poll.ConnectionFactory")
    @patch("web.api.burp_poll.create_llm_provider")
    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.ConfigManager")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_202_and_starts_thread(
        self,
        mock_registry_fn,
        mock_config_cls,
        mock_resolve,
        mock_llm,
        mock_conn_factory,
        mock_create_finding,
        mock_ingest_cls,
        mock_state_repo_cls,
        mock_mcp_client_cls,
        mock_poller_cls,
        mock_thread_cls,
    ):
        app, cfg_manager = _make_app()
        mock_config_cls.return_value = cfg_manager
        mock_resolve.return_value = _project_row()

        registry = MagicMock()
        registry.get_for_project.return_value = None
        mock_registry_fn.return_value = registry

        mock_llm.side_effect = Exception("no LLM")

        mock_factory = MagicMock()
        mock_conn_factory.return_value = mock_factory

        client = TestClient(app)
        resp = client.post("/api/v1/projects/1/burp/poll")

        assert resp.status_code == 202
        body = resp.json()
        assert body["project_id"] == 1
        assert body["status"] == "polling"
        registry.register.assert_called_once()
        mock_thread_cls.return_value.start.assert_called_once()


class TestStartPollConflict:
    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.ConfigManager")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_409_when_already_polling(
        self,
        mock_registry_fn,
        mock_config_cls,
        mock_resolve,
    ):
        app, cfg_manager = _make_app()
        mock_config_cls.return_value = cfg_manager
        mock_resolve.return_value = _project_row()

        registry = MagicMock()
        registry.get_for_project.return_value = MagicMock()
        mock_registry_fn.return_value = registry

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/projects/1/burp/poll")
        assert resp.status_code == 409


class TestStartPollNoConfig:
    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.ConfigManager")
    def test_returns_422_without_burp_config(
        self,
        mock_config_cls,
        mock_resolve,
    ):
        app, _ = _make_app(burp_mcp_url="")
        cfg_manager = MagicMock()
        cfg_manager.global_config.burp = None
        mock_config_cls.return_value = cfg_manager
        mock_resolve.return_value = _project_row()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/projects/1/burp/poll")
        assert resp.status_code == 422


class TestCancelPoll:
    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_202_and_sets_cancel_token(
        self,
        mock_registry_fn,
        mock_resolve,
    ):
        app, _ = _make_app()
        mock_resolve.return_value = _project_row()

        cancel_token = MagicMock()
        handle = MagicMock()
        handle.cancel_token = cancel_token
        registry = MagicMock()
        registry.get_for_project.return_value = handle
        mock_registry_fn.return_value = registry

        client = TestClient(app)
        resp = client.post("/api/v1/projects/1/burp/poll/cancel")
        assert resp.status_code == 202
        cancel_token.set.assert_called_once()

    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_404_when_not_polling(
        self,
        mock_registry_fn,
        mock_resolve,
    ):
        app, _ = _make_app()
        mock_resolve.return_value = _project_row()

        registry = MagicMock()
        registry.get_for_project.return_value = None
        mock_registry_fn.return_value = registry

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/projects/1/burp/poll/cancel")
        assert resp.status_code == 404


class TestPollStatus:
    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.ConfigManager")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_active_when_polling(
        self,
        mock_registry_fn,
        mock_config_cls,
        mock_resolve,
    ):
        app, cfg_manager = _make_app()
        mock_config_cls.return_value = cfg_manager
        mock_resolve.return_value = _project_row()

        registry = MagicMock()
        registry.get_for_project.return_value = MagicMock()
        mock_registry_fn.return_value = registry

        client = TestClient(app)
        resp = client.get("/api/v1/projects/1/burp/poll/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["active"] is True

    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.ConfigManager")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_inactive_when_not_polling(
        self,
        mock_registry_fn,
        mock_config_cls,
        mock_resolve,
    ):
        app, cfg_manager = _make_app()
        mock_config_cls.return_value = cfg_manager
        mock_resolve.return_value = _project_row()

        registry = MagicMock()
        registry.get_for_project.return_value = None
        mock_registry_fn.return_value = registry

        client = TestClient(app)
        resp = client.get("/api/v1/projects/1/burp/poll/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["active"] is False

    @patch("web.api.burp_poll._resolve_project")
    @patch("web.api.burp_poll.ConfigManager")
    @patch("web.api.burp_poll.get_burp_poll_registry")
    def test_returns_not_configured(
        self,
        mock_registry_fn,
        mock_config_cls,
        mock_resolve,
    ):
        app, _ = _make_app(burp_mcp_url="")
        cfg_manager = MagicMock()
        cfg_manager.global_config.burp = None
        mock_config_cls.return_value = cfg_manager
        mock_resolve.return_value = _project_row()

        registry = MagicMock()
        registry.get_for_project.return_value = None
        mock_registry_fn.return_value = registry

        client = TestClient(app)
        resp = client.get("/api/v1/projects/1/burp/poll/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["active"] is False

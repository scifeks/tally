"""Unit tests for the Burp scan endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api._errors import install_error_handlers
from web.api.burp_scan import v1_router


def _make_app(
    project_registry=None,
    tool_registry=None,
    event_bus=None,
    base_path="/tmp/test",
):
    app = FastAPI()
    install_error_handlers(app)
    app.state.project_registry = project_registry or MagicMock()
    app.state.tool_registry = tool_registry or MagicMock()
    app.state.event_bus = event_bus or MagicMock()
    app.state.base_path = base_path
    app.include_router(v1_router, prefix="/api/v1/projects")
    return app


class TestBurpScanEndpoint:
    def test_returns_202_with_run_id(self):
        registry = MagicMock()
        project_reg = MagicMock()
        row = MagicMock()
        row.id = 1
        row.name = "testproject"
        row.path = "/tmp/test/projects/testproject"
        project_reg.resolve.return_value = row

        app = _make_app(
            project_registry=project_reg,
            tool_registry=registry,
        )
        client = TestClient(app)

        mock_handle = MagicMock()
        mock_handle.run_id = 42

        mock_run_row = MagicMock()
        mock_run_row.id = 42
        mock_run_row.project_id = 1
        mock_run_row.status = "running"
        mock_run_row.started_at = None
        mock_run_row.finished_at = None
        mock_run_row.repo_ids = []
        mock_run_row.tool_ids = ["burp"]
        mock_run_row.domains = ["web"]
        mock_run_row.findings_count = 0
        mock_run_row.skip_enrichment = False

        mock_cfg = MagicMock()
        mock_cfg.global_config.burp = MagicMock()

        with (
            patch(
                "web.api.burp_scan._resolve_project",
                return_value=row,
            ),
            patch(
                "web.api.burp_scan._collect_base_urls",
                return_value=["https://target.example.com"],
            ),
            patch(
                "core.config.manager.ConfigManager",
                return_value=mock_cfg,
            ),
            patch(
                "web.api.burp_scan.get_scan_service",
            ) as mock_svc,
            patch(
                "web.api.burp_scan.create_scan_repos",
            ) as mock_repos,
            patch(
                "web.api.burp_scan.create_finding_repo",
            ),
            patch(
                "web.api.burp_scan.create_repo_repo",
            ),
            patch(
                "web.api.burp_scan.create_url_finding_repo",
            ),
        ):
            mock_svc.return_value.start_scan.return_value = mock_handle
            mock_repos.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )
            mock_repos.return_value[0].get.return_value = mock_run_row

            resp = client.post(
                "/api/v1/projects/1/burp-scan",
                json={},
            )

        assert resp.status_code == 202

    def test_returns_422_when_no_base_urls(self):
        project_reg = MagicMock()
        row = MagicMock()
        row.id = 1
        row.name = "testproject"
        row.path = "/tmp/test/projects/testproject"
        project_reg.resolve.return_value = row

        app = _make_app(project_registry=project_reg)
        client = TestClient(app)

        with (
            patch(
                "web.api.burp_scan._resolve_project",
                return_value=row,
            ),
            patch(
                "web.api.burp_scan._collect_base_urls",
                return_value=[],
            ),
        ):
            resp = client.post(
                "/api/v1/projects/1/burp-scan",
                json={},
            )

        assert resp.status_code == 422

    def test_returns_422_when_burp_not_configured(self):
        project_reg = MagicMock()
        row = MagicMock()
        row.id = 1
        row.name = "testproject"
        row.path = "/tmp/test/projects/testproject"
        project_reg.resolve.return_value = row

        app = _make_app(project_registry=project_reg)
        client = TestClient(app)

        mock_cfg = MagicMock()
        mock_cfg.global_config.burp = None

        with (
            patch(
                "web.api.burp_scan._resolve_project",
                return_value=row,
            ),
            patch(
                "web.api.burp_scan._collect_base_urls",
                return_value=["https://target.example.com"],
            ),
            patch(
                "core.config.manager.ConfigManager",
                return_value=mock_cfg,
            ),
        ):
            resp = client.post(
                "/api/v1/projects/1/burp-scan",
                json={},
            )

        assert resp.status_code == 422

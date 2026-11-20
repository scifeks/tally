"""Integration tests for background scan start and resume endpoints."""

from __future__ import annotations

import json
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.locking import get_registry
from application.tools.scan_run_registry import get_scan_run_registry
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


def _seed_global_config(base_path: str) -> None:
    """Write minimal config files so ConfigManager works."""
    config_dir = Path(base_path) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "model": "test-model",
                    "base_url": "http://localhost:11434",
                },
                "embedding_inference": {
                    "provider": "ollama",
                    "model": "test-embed",
                },
                "claude": {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "sk-test-key",
                    "default_billing_method": "plan",
                },
                "mcp": {
                    "host": "127.0.0.1",
                    "port": 8765,
                },
            }
        )
    )


def _seed_project_repos(base_path: str, project_name: str) -> None:
    """Seed an active repo row for the project so load_active_repos works."""
    from core.config.schemas.repo_service import RepoService
    from core.config.schemas.repository import Repository
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.repositories import RepositoryRepository

    repo_path = Path(base_path) / "fake-repo"
    repo_path.mkdir(parents=True, exist_ok=True)
    project_dir = Path(base_path) / "projects" / project_name
    config_dir = project_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "project.json").write_text(
        json.dumps(
            {
                "project_name": project_name,
                "created": "2026-04-25T00:00:00",
            }
        )
    )
    sqlite_dir = project_dir / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(sqlite_dir / "findings.db")
    factory.init_schema()
    RepositoryRepository(factory).insert(
        Repository(
            name="test-repo",
            path=str(repo_path),
            services=[
                RepoService(
                    name="default",
                    type=["api"],
                    languages=["python"],
                )
            ],
        )
    )


@pytest.fixture(autouse=True)
def _reset_scan_state():
    """Reset process-singleton scan state between tests."""
    get_scan_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("scan") is not None:  # type: ignore[attr-defined]
        reg._jobs["scan"] = None  # type: ignore[attr-defined,index]
    yield
    get_scan_run_registry().reset()
    if reg._jobs.get("scan") is not None:  # type: ignore[attr-defined]
        reg._jobs["scan"] = None  # type: ignore[attr-defined,index]


def _mock_launcher() -> MagicMock:
    """Build a mock ScanBackgroundLauncher that returns a resolved future."""
    launcher = MagicMock()
    fut: Future[str] = Future()
    fut.set_result("done")
    handle = MagicMock()
    handle.result = fut
    launcher.launch.return_value = handle
    return launcher


def _seed_run(factory, *, project_id: int, **overrides: Any) -> int:
    repo = RunRepository(factory)
    return repo.create(
        project_id=project_id,
        repo_ids=overrides.get("repo_ids", ["test-repo"]),
        tool_ids=overrides.get("tool_ids", ["claudecode"]),
        domains=overrides.get("domains", ["llm"]),
        skip_enrichment=overrides.get("skip_enrichment", True),
        status=overrides.get("status", "queued"),
    )


class TestStartBackgroundScan:
    @pytest.mark.asyncio
    async def test_start_scan_background_returns_202(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
                "only_scanner_skills": ["scan-xss-stored"],
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["interaction_mode"] == "background"
        assert body["status"] == "queued"
        assert isinstance(body["id"], int)

        launcher.launch.assert_called_once()
        call_kwargs = launcher.launch.call_args.kwargs
        assert call_kwargs["interaction_mode"] == "background"
        assert call_kwargs["only"] == ["scan-xss-stored"]

    @pytest.mark.asyncio
    async def test_start_scan_rejects_only_and_exclude_together(
        self, app_client
    ) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
                "only_scanner_skills": ["scan-xss-stored"],
                "exclude_scanner_skills": ["scan-injection-sql"],
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_start_scan_rejects_unknown_scanner_skill(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
                "only_scanner_skills": ["scan-nonexistent-skill"],
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_start_scan_expands_family_names(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """Family names like 'xss' expand to per-scanner display slugs."""
        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
                "only_scanner_skills": ["xss"],
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text

        call_kwargs = launcher.launch.call_args.kwargs
        only = call_kwargs["only"]
        assert "scan-xss-stored" in only
        assert "scan-xss-reflected" in only
        assert "scan-xss-blind" in only

    @pytest.mark.asyncio
    async def test_start_scan_background_billing_validation_error(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """ValueError from the launcher (billing unavailable) returns 400."""
        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        launcher = _mock_launcher()
        launcher.launch.side_effect = ValueError("plan billing unavailable: no session")
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_start_scan_background_no_active_repos_400(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """ScanConfigurationError (no active repos) returns 400."""
        from application.scans.background_launcher import ScanConfigurationError

        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        launcher = _mock_launcher()
        launcher.launch.side_effect = ScanConfigurationError("no active repos")
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_interactive_mode_unchanged(self, app_client, monkeypatch) -> None:
        """Default interaction_mode='interactive' still uses the existing path."""
        client, _fid, _kb, _factory, muth, project_id = app_client

        spawned: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: spawned.append(kw),
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={"repoIds": [], "toolIds": [], "domains": []},
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert len(spawned) == 1


class TestResumeScan:
    @pytest.mark.asyncio
    async def test_resume_scan_returns_202(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        run_id = _seed_run(factory, project_id=project_id, status="failed")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        # Mock get_scan_config to return existing config
        monkeypatch.setattr(
            "application.mcp.ingest_service.McpIngestService.get_scan_config",
            lambda self, project, run_id: {
                "is_configured": True,
                "only": ["scan-xss-stored"],
                "exclude": [],
                "adversarial_verification": False,
            },
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
            json={
                "interaction_mode": "background",
                "billing_method": "api",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["interaction_mode"] == "background"
        assert body["status"] == "running"
        assert body["id"] == run_id

    @pytest.mark.asyncio
    async def test_resume_scan_404_for_missing_run(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/9999/resume",
            json={
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_scan_billing_error_400(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        run_id = _seed_run(factory, project_id=project_id, status="rate_limited")

        launcher = _mock_launcher()
        launcher.launch.side_effect = ValueError("api billing unavailable: no key")
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )
        monkeypatch.setattr(
            "application.mcp.ingest_service.McpIngestService.get_scan_config",
            lambda self, project, run_id: {
                "is_configured": True,
                "only": [],
                "exclude": [],
                "adversarial_verification": False,
            },
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
            json={
                "interaction_mode": "background",
                "billing_method": "api",
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_resume_completed_run_returns_400(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """A completed run is not resumable."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))

        run_id = _seed_run(factory, project_id=project_id, status="done")

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
            json={"interaction_mode": "background"},
            headers=muth,
        )
        assert resp.status_code == 400
        assert "cannot resume" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_resume_with_api_key_override(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """api_key_override is forwarded to the launcher as api_key_source."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        run_id = _seed_run(factory, project_id=project_id, status="failed")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )
        monkeypatch.setattr(
            "application.mcp.ingest_service.McpIngestService.get_scan_config",
            lambda self, project, run_id: {
                "is_configured": True,
                "only": [],
                "exclude": [],
                "adversarial_verification": False,
            },
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
            json={
                "interaction_mode": "background",
                "api_key_override": "sk-override-123",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        call_kwargs = launcher.launch.call_args.kwargs
        assert call_kwargs["api_key_source"] == "sk-override-123"

    @pytest.mark.asyncio
    async def test_resume_without_override_uses_config_key(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """Without api_key_override the config key is used."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        run_id = _seed_run(factory, project_id=project_id, status="failed")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )
        monkeypatch.setattr(
            "application.mcp.ingest_service.McpIngestService.get_scan_config",
            lambda self, project, run_id: {
                "is_configured": True,
                "only": [],
                "exclude": [],
                "adversarial_verification": False,
            },
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
            json={"interaction_mode": "background"},
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        call_kwargs = launcher.launch.call_args.kwargs
        assert call_kwargs["api_key_source"] == "sk-test-key"

    @pytest.mark.asyncio
    async def test_resume_updates_run_status_to_running(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """After resume the persisted status should be 'running'."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        run_id = _seed_run(factory, project_id=project_id, status="failed")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )
        monkeypatch.setattr(
            "application.mcp.ingest_service.McpIngestService.get_scan_config",
            lambda self, project, run_id: {
                "is_configured": True,
                "only": [],
                "exclude": [],
                "adversarial_verification": False,
            },
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
            json={"interaction_mode": "background"},
            headers=muth,
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "running"

        # Verify the DB row was updated
        repo = RunRepository(factory)
        row = repo.get(run_id)
        assert row is not None
        assert row.status == "running"


class TestInteractiveFieldRejection:
    @pytest.mark.asyncio
    async def test_interactive_rejects_billing_method(self, app_client) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "interactive",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        msg = resp.json()["error"]["message"]
        assert "require interaction_mode='background'" in msg

    @pytest.mark.asyncio
    async def test_interactive_rejects_only_scanner_skills(self, app_client) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "interactive",
                "only_scanner_skills": ["scan-xss-stored"],
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_interactive_rejects_adversarial(self, app_client) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "interactive",
                "adversarial_verification": True,
            },
            headers=muth,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_interactive_allows_empty_background_fields(
        self, app_client, monkeypatch
    ) -> None:
        """Default/empty background fields should not trigger rejection."""
        client, _fid, _kb, _factory, muth, project_id = app_client

        spawned: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: spawned.append(kw),
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "interactive",
                "billing_method": None,
                "only_scanner_skills": [],
                "exclude_scanner_skills": [],
                "adversarial_verification": False,
            },
            headers=muth,
        )
        assert resp.status_code == 202


class TestStartApiKeyOverride:
    @pytest.mark.asyncio
    async def test_start_with_api_key_override(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_project_repos(str(tmp_path), "testproject")

        launcher = _mock_launcher()
        monkeypatch.setattr(
            "web.api.scans._build_background_launcher",
            lambda request, paths: launcher,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "interaction_mode": "background",
                "billing_method": "api",
                "api_key_override": "sk-custom-key",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        call_kwargs = launcher.launch.call_args.kwargs
        assert call_kwargs["api_key_source"] == "sk-custom-key"

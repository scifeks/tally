"""Integration tests for triage start/resume with interaction_mode
and billing_method."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from application.locking import get_registry
from application.triage.run_registry import get_triage_run_registry
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


def _seed_global_config(base_path: str) -> None:
    """Write config with claude + triage_inference so background mode resolves."""
    config_dir = Path(base_path) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "triage_agent_provider": "claude_code",
                "ollama": {
                    "model": "test-model",
                    "base_url": "http://localhost:11434",
                },
                "embedding_inference": {
                    "provider": "ollama",
                    "model": "test-embed",
                },
                "triage_inference": {
                    "provider": "ollama",
                },
                "claude": {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "sk-test-key",
                    "default_billing_method": "plan",
                },
            }
        )
    )


def _seed_scan_run(factory, *, project_id: int, status: str = "done") -> int:
    repo = RunRepository(factory)
    return repo.create(
        project_id=project_id,
        repo_ids=["test-repo"],
        tool_ids=[],
        domains=["code"],
        skip_enrichment=False,
        status=status,
    )


def _seed_triage_batch(
    factory,
    *,
    run_id: int,
    finding_ids: list[int],
    status: str = "pending",
) -> int:
    batch_data: list[dict[str, Any]] = [
        {"id": fid, "tool": "semgrep", "segment": "sast"} for fid in finding_ids
    ]
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts,"
            "  started_at, completed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                json.dumps(finding_ids),
                json.dumps(batch_data),
                status,
                0,
                None,
                None,
            ),
        )
        return cur.lastrowid


@pytest.fixture(autouse=True)
def _reset_triage_state():
    """Reset process-singleton triage state between tests."""
    get_triage_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("triage") is not None:  # type: ignore[attr-defined]
        reg._jobs["triage"] = None  # type: ignore[attr-defined,index]
    yield
    get_triage_run_registry().reset()
    if reg._jobs.get("triage") is not None:  # type: ignore[attr-defined]
        reg._jobs["triage"] = None  # type: ignore[attr-defined,index]


class TestStartTriageBackground:
    @pytest.mark.asyncio
    async def test_start_background_plan_returns_202(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import TriageService

        started: dict[str, Any] = {}

        def fake_run_worker(self, **kwargs: Any) -> None:
            started.update(kwargs)

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["scan_run_id"] is not None

    @pytest.mark.asyncio
    async def test_start_background_api_returns_202(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import TriageService

        started: dict[str, Any] = {}

        def fake_run_worker(self, **kwargs: Any) -> None:
            started.update(kwargs)

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "api",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text

    @pytest.mark.asyncio
    async def test_start_interactive_returns_202(self, app_client, monkeypatch) -> None:
        """Default interactive mode still works without mode args."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_scan_run(factory, project_id=project_id)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        from application.triage.triage_service import TriageService

        def fake_run_worker(self, **kwargs: Any) -> None:
            pass

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)
        monkeypatch.setattr(
            "application.mcp.token_minting.mint_bearer_token",
            lambda tag, base_path: "tok-interactive",
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "mcp_bearer_token" in body
        assert "mcp_url" in body

    @pytest.mark.asyncio
    async def test_start_with_api_key_override(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """api_key_override is forwarded to the service."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import TriageService

        started: dict[str, Any] = {}

        def fake_run_worker(self, **kwargs: Any) -> None:
            started.update(kwargs)

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "api",
                "api_key_override": "sk-custom-key",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text


class TestStartTriageSemanticValidation:
    @pytest.mark.asyncio
    async def test_interactive_rejects_billing_method(self, app_client) -> None:
        client, _fid, _kb, _factory, muth, project_id = app_client

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        msg = resp.json()["error"]["message"]
        assert "require interaction_mode='background'" in msg

    @pytest.mark.asyncio
    async def test_interactive_allows_null_billing(
        self, app_client, monkeypatch
    ) -> None:
        """Default/null billing_method should not trigger rejection."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_scan_run(factory, project_id=project_id)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        from application.triage.triage_service import TriageService

        def fake_run_worker(self, **kwargs: Any) -> None:
            pass

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)
        monkeypatch.setattr(
            "application.mcp.token_minting.mint_bearer_token",
            lambda tag, base_path: "tok-null-billing",
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
                "billing_method": None,
            },
            headers=muth,
        )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_configuration_error_returns_400(
        self, app_client, monkeypatch
    ) -> None:
        """TriageConfigurationError from the service maps to 400."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import (
            TriageConfigurationError,
            TriageService,
        )

        def fake_start(self, **kwargs: Any) -> None:
            raise TriageConfigurationError("bad config combo")

        monkeypatch.setattr(TriageService, "start_triage", fake_start)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        assert "bad config combo" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_credential_error_returns_400(self, app_client, monkeypatch) -> None:
        """TriageCredentialsError from credential validation maps to 400."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import (
            TriageCredentialsError,
            TriageService,
        )

        def fake_start(self, **kwargs: Any) -> None:
            raise TriageCredentialsError("plan billing unavailable: no session")

        monkeypatch.setattr(TriageService, "start_triage", fake_start)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        assert "plan billing unavailable" in resp.json()["error"]["message"]


class TestResumeTriageBackground:
    @pytest.mark.asyncio
    async def test_resume_background_returns_202(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

        from application.triage.triage_service import TriageService

        started: dict[str, Any] = {}

        def fake_run_worker(self, **kwargs: Any) -> None:
            started.update(kwargs)

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "api",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["scan_run_id"] == run_id
        assert body["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_resume_rate_limited_returns_202(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """rate_limited is a resumable status."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(
            factory, run_id=run_id, finding_ids=[1], status="rate_limited"
        )

        from application.triage.triage_service import TriageService

        def fake_run_worker(self, **kwargs: Any) -> None:
            pass

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text

    @pytest.mark.asyncio
    async def test_resume_with_api_key_override(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

        from application.triage.triage_service import TriageService

        started: dict[str, Any] = {}

        def fake_run_worker(self, **kwargs: Any) -> None:
            started.update(kwargs)

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "api_key_override": "sk-override-123",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text

    @pytest.mark.asyncio
    async def test_resume_interactive_rejects_billing_method(self, app_client) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        msg = resp.json()["error"]["message"]
        assert "require interaction_mode='background'" in msg

    @pytest.mark.asyncio
    async def test_resume_credential_error_returns_400(
        self, app_client, monkeypatch
    ) -> None:
        """TriageCredentialsError from resume credential validation maps to 400."""
        client, _fid, _kb, factory, muth, project_id = app_client
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

        from application.triage.triage_service import (
            TriageCredentialsError,
            TriageService,
        )

        def fake_resume(self, **kwargs: Any) -> None:
            raise TriageCredentialsError("api billing unavailable: no key")

        monkeypatch.setattr(TriageService, "resume_triage", fake_resume)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "api",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        assert "api billing unavailable" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_resume_completed_returns_409(self, app_client, tmp_path) -> None:
        """A completed run is not resumable."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="completed")

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "TRIAGE_NOT_RESUMABLE"


class TestInteractiveApiKeyOverrideRejection:
    """api_key_override is background-only; interactive mode must reject it."""

    @pytest.mark.asyncio
    async def test_start_interactive_rejects_api_key_override(self, app_client) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_scan_run(factory, project_id=project_id)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
                "api_key_override": "sk-x",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        assert "api_key_override" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_resume_interactive_rejects_api_key_override(
        self, app_client
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
                "api_key_override": "sk-x",
            },
            headers=muth,
        )
        assert resp.status_code == 400
        assert "api_key_override" in resp.json()["error"]["message"]


class TestInteractiveMcpConnection:
    """Interactive triage must return MCP connection info."""

    @pytest.mark.asyncio
    async def test_start_interactive_returns_mcp_bearer_token(
        self, app_client, monkeypatch
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_scan_run(factory, project_id=project_id)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        from application.triage.triage_service import TriageService

        def fake_run_worker(self, **kwargs: Any) -> None:
            pass

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        # Stub token minting so we don't need a real tally.db/key file.
        monkeypatch.setattr(
            "application.mcp.token_minting.mint_bearer_token",
            lambda tag, base_path: "tok-test-123",
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "mcp_bearer_token" in body
        assert isinstance(body["mcp_bearer_token"], str)
        assert body["mcp_bearer_token"] != ""
        assert "mcp_url" in body
        assert body["mcp_url"].startswith("http")

    @pytest.mark.asyncio
    async def test_resume_interactive_returns_mcp_bearer_token(
        self, app_client, monkeypatch
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        run_id = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        from application.triage.triage_service import TriageService

        def fake_run_worker(self, **kwargs: Any) -> None:
            pass

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        monkeypatch.setattr(
            "application.mcp.token_minting.mint_bearer_token",
            lambda tag, base_path: "tok-resume-456",
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "interactive",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "mcp_bearer_token" in body
        assert body["mcp_bearer_token"] != ""
        assert "mcp_url" in body

    @pytest.mark.asyncio
    async def test_background_start_does_not_return_mcp_connection(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        """Background mode should not include MCP connection fields."""
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import TriageService

        def fake_run_worker(self, **kwargs: Any) -> None:
            pass

        monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "plan",
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "mcp_bearer_token" not in body
        assert "mcp_url" not in body


class TestStartTriageArgumentForwarding:
    """Pin argument forwarding from the handler to TriageService.start_triage."""

    @pytest.mark.asyncio
    async def test_start_forwards_all_args_to_service(
        self, app_client, monkeypatch, tmp_path
    ) -> None:
        client, _fid, _kb, factory, muth, project_id = app_client
        _seed_global_config(str(tmp_path))
        run_id = _seed_scan_run(factory, project_id=project_id)

        from application.triage.triage_service import TriageService

        captured: dict[str, Any] = {}

        def spy_start(self, **kwargs: Any):
            captured.update(kwargs)
            # Skip actual dispatch to avoid thread spawning.
            from unittest.mock import MagicMock

            return MagicMock(scan_run_id=kwargs.get("scan_run_id", run_id))

        monkeypatch.setattr(TriageService, "start_triage", spy_start)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage",
            json={
                "acknowledge_injection_risk": True,
                "interaction_mode": "background",
                "billing_method": "api",
                "api_key_override": "sk-forwarded",
                "scan_run_id": run_id,
            },
            headers=muth,
        )
        assert resp.status_code == 202, resp.text
        assert captured["interaction_mode"] == "background"
        assert captured["billing_method"] == "api"
        assert captured["api_key"] == "sk-forwarded"
        assert captured["scan_run_id"] == run_id

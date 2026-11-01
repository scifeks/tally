"""E2E test: background scan resume after rate limit.

Fakes only _run_sdk_skill. Every other layer (ScanBackgroundLauncher,
McpIngestService, FastAPI routes, repositories) runs for real. The test
fires a background scan with billing=plan, scripts recon to complete and
domain:injection to rate_limit, then resumes with billing=api. Asserts
that recon has one attempt, domain:injection has two (plan rate_limited
then api completed), and domain:xss has one api attempt.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from application.mcp.ingest_service import McpIngestService
from infrastructure.events.bus import EventBus
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests._app_factory import build_test_app
from tests.e2e.scan._harness import FakeSkillRunner
from web.adapters.event_bus_scan_sink import EventBusScanSink

pytestmark = pytest.mark.e2e

_TEST_PORT = 12398
_HANDSHAKE = "e2e-scan-resume-handshake"
_PROJECT_NAME = "scanproject"


def _seed_global_config(base_path: Path) -> None:
    """Write config that satisfies background mode requirements."""
    config_dir = base_path / "config"
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
                    "provider": "claude",
                },
                "claude": {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "sk-test-e2e-scan",
                },
            }
        )
    )


async def _authenticate(client: httpx.AsyncClient) -> dict[str, str]:
    """Exchange handshake for session cookies."""
    resp = await client.post(
        "/api/v1/auth/exchange",
        json={"token": _HANDSHAKE},
        headers={"origin": f"https://127.0.0.1:{_TEST_PORT}"},
    )
    assert resp.status_code == 200, f"exchange failed: {resp.text}"
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    csrf_token = client.cookies["tally_csrf"]
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": f"https://127.0.0.1:{_TEST_PORT}",
    }


def _wait_for_phase_status(
    factory: ConnectionFactory,
    run_id: int,
    phase: str,
    expected_status: str,
    *,
    timeout: float = 30.0,
) -> None:
    """Poll scan_phase_executions until *phase* reaches *expected_status*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = ?"
                " ORDER BY attempt_number DESC LIMIT 1",
                (run_id, phase),
            ).fetchone()
        if row is not None and row["status"] == expected_status:
            return
        time.sleep(0.15)
    pytest.fail(
        f"Timed out waiting for phase {phase!r} to reach {expected_status!r}"
        f" (run_id={run_id})"
    )


def _wait_for_run_status(
    factory: ConnectionFactory,
    run_id: int,
    expected_status: str,
    *,
    timeout: float = 30.0,
) -> None:
    """Poll scan_runs until *run_id* reaches *expected_status*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM scan_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is not None and row["status"] == expected_status:
            return
        time.sleep(0.15)
    pytest.fail(f"Timed out waiting for run {run_id} to reach {expected_status!r}")


@pytest_asyncio.fixture()
async def scan_e2e_env(tmp_path: Path, monkeypatch):
    """Build a lightweight test environment for background SDK scans."""
    _seed_global_config(tmp_path)

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token-ignored-by-fake-sdk")

    db_path = tmp_path / "projects" / _PROJECT_NAME / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    # Seed a repository row so load_active_repos finds a repo with a path.
    repo_dir = tmp_path / "repos" / "testrepo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO repositories (name, path, services_json) VALUES (?, ?, ?)",
            ("testrepo", str(repo_dir), json.dumps([{"name": "default"}])),
        )

    app = build_test_app(tmp_path, _HANDSHAKE, port=_TEST_PORT)

    project_id = app.state.project_registry.register(_PROJECT_NAME, str(tmp_path))

    bus = EventBus()
    await bus.register_job("triage", "triage")
    await bus.register_job("finding", "finding")
    await bus.register_job("scan", "scan")
    await bus.register_job("report", "report")
    await bus.register_job("report_draft", "report_draft")
    await bus.register_job("chat", "chat")
    app.state.event_bus = bus

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    sink = EventBusScanSink(bus)
    ingest_service = McpIngestService(
        finding_repo=finding_repo,
        run_repo=run_repo,
        scan_event_sink=sink,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"https://127.0.0.1:{_TEST_PORT}",
    ) as client:
        mut_headers = await _authenticate(client)
        yield {
            "client": client,
            "mut_headers": mut_headers,
            "factory": factory,
            "project_id": project_id,
            "project_name": _PROJECT_NAME,
            "ingest_service": ingest_service,
            "base_path": tmp_path,
        }


@pytest.fixture(autouse=True)
def _reset_scan_singletons():
    """Reset process-wide scan state between tests."""
    from application.tools.scan_run_registry import get_scan_run_registry

    get_scan_run_registry().reset()
    yield
    get_scan_run_registry().reset()


class TestBackgroundScanResume:
    @pytest.mark.asyncio
    async def test_resume_skips_completed_phases(
        self, scan_e2e_env: dict[str, Any]
    ) -> None:
        env = scan_e2e_env
        client: httpx.AsyncClient = env["client"]
        factory: ConnectionFactory = env["factory"]
        project_id: int = env["project_id"]
        ingest_service = env["ingest_service"]
        project_name: str = env["project_name"]

        controller = FakeSkillRunner(
            ingest_service=ingest_service,
            project_name=project_name,
        )

        # First launch: recon completes, domain:injection hits rate limit.
        controller.on_phase("recon").mark_complete()
        controller.on_phase("domain:injection").raise_rate_limit_plan()

        with controller.active():
            resp = await client.post(
                f"/api/v1/projects/{project_id}/scans",
                json={
                    "interaction_mode": "background",
                    "billing_method": "plan",
                },
                headers=env["mut_headers"],
            )
            assert resp.status_code == 202, resp.text
            run_id: int = resp.json()["id"]

            _wait_for_phase_status(factory, run_id, "domain:injection", "rate_limited")

        # Wait for the worker to write the terminal run status.
        _wait_for_run_status(factory, run_id, "rate_limited")

        # Resume on api billing with fresh scripted outcomes.
        controller.reset()
        controller.on_phase("domain:injection").mark_complete()
        controller.on_phase("domain:xss").mark_complete()

        with controller.active():
            resp = await client.post(
                f"/api/v1/projects/{project_id}/scans/{run_id}/resume",
                json={
                    "interaction_mode": "background",
                    "billing_method": "api",
                },
                headers=env["mut_headers"],
            )
            assert resp.status_code == 202, resp.text

            _wait_for_phase_status(factory, run_id, "domain:xss", "completed")

        # Verify the resume preamble was passed on the second launch.
        assert len(controller.calls) == 2
        first_prompt = controller.calls[0]["prompt"]
        second_prompt = controller.calls[1]["prompt"]
        assert "Resume:" not in first_prompt
        assert "Resume: phases already completed: [recon]" in second_prompt

        # Verify the execution history.
        with factory.connect() as conn:
            all_rows = conn.execute(
                "SELECT phase, attempt_number, usage_pool, status"
                " FROM scan_phase_executions WHERE run_id = ?"
                " ORDER BY phase, attempt_number",
                (run_id,),
            ).fetchall()

        recon = [r for r in all_rows if r["phase"] == "recon"]
        injection = [r for r in all_rows if r["phase"] == "domain:injection"]
        xss = [r for r in all_rows if r["phase"] == "domain:xss"]

        assert len(recon) == 1
        assert (recon[0]["usage_pool"], recon[0]["status"]) == (
            "plan",
            "completed",
        )

        assert len(injection) == 2
        assert (injection[0]["usage_pool"], injection[0]["status"]) == (
            "plan",
            "rate_limited",
        )
        assert (injection[1]["usage_pool"], injection[1]["status"]) == (
            "api",
            "completed",
        )

        assert len(xss) == 1
        assert (xss[0]["usage_pool"], xss[0]["status"]) == (
            "api",
            "completed",
        )

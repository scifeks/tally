"""E2E test: background triage auto-failover from plan to api.

Fakes only _run_sdk_once. Every other layer (TriageService, TriageRunner,
repositories, FastAPI route) runs for real. The test seeds a project with
one SAST finding, POSTs background triage with no explicit billing_method
(triggering auto-failover eligibility), scripts a RATE_LIMIT_PLAN on the
first SDK call and a valid verdict on the second, then asserts the two
triage_batch_executions rows are (plan, rate_limited) and (api, completed).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from infrastructure.events.bus import EventBus
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests._app_factory import build_test_app
from tests.e2e.triage._harness import FakeSdkController
from tests.finding_helpers import normalize_test_findings

pytestmark = pytest.mark.e2e

_TEST_PORT = 12399
_HANDSHAKE = "e2e-failover-handshake"

_PROJECT_NAME = "testproject"

_SAST_FINDING: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "segment": "sast",
    "severity": "high",
    "file_path": "src/app.py",
    "rule_id": "python.lang.security.audit.sqli",
    "description": "SQL injection risk",
    "repo": "testrepo",
    "type_vulnerability": True,
    "profile": _PROJECT_NAME,
    "remediation": "use parameterized queries",
    "author": "dev",
    "commit": "abc123",
}


def _seed_global_config(base_path: Path) -> None:
    """Write config that satisfies background mode requirements.

    triage_inference points to "claude" so resolve_triage_config reads
    the claude block for model/timeout. The background path overrides
    provider_name to "claude_sdk" regardless.
    """
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
                    "api_key": "sk-test-e2e",
                },
            }
        )
    )


def _seed_commands_config(base_path: Path) -> None:
    """Register semgrep so the triage runner's tool lookup succeeds."""
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "semgrep": {
                    "type": "repo",
                    "location": "docker",
                    "container": {
                        "name": "tally-test-semgrep",
                        "tool_path": "/usr/bin/semgrep",
                    },
                }
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


def _wait_for_executions(
    factory: ConnectionFactory,
    scan_run_id: int,
    *,
    expect_count: int,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Poll triage_batch_executions until *expect_count* terminal rows appear."""
    rows: list = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT e.usage_pool, e.status, e.attempt_number"
                " FROM triage_batch_executions e"
                " JOIN triage_batches b ON b.id = e.batch_id"
                " WHERE b.run_id = ?"
                " ORDER BY e.attempt_number",
                (scan_run_id,),
            ).fetchall()
        terminal = [dict(r) for r in rows if r["status"] not in ("in_progress",)]
        if len(terminal) >= expect_count:
            return terminal
        time.sleep(0.15)
    pytest.fail(
        f"Timed out waiting for {expect_count} terminal execution rows"
        f" (scan_run_id={scan_run_id}); got {len(rows)} total rows"
    )


@pytest_asyncio.fixture()
async def background_triage_env(tmp_path: Path, monkeypatch):
    """Build a lightweight test environment for background SDK triage.

    Seeds config, DB, project, one SAST finding, and a fake tool registry
    entry for semgrep. Monkeypatches OAuth detection to report available.
    """
    _seed_global_config(tmp_path)
    _seed_commands_config(tmp_path)

    # The real detect_oauth_session honors this env var and returns
    # available=True when set, bypassing `claude auth status`.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token-ignored-by-fake-sdk")

    db_path = tmp_path / "projects" / _PROJECT_NAME / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    # Seed a repository row so the triage batching query succeeds.
    # services_json must have at least one entry or the Repository
    # pydantic validator rejects it.
    repo_dir = tmp_path / "repos" / "testrepo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, path, services_json) VALUES (?, ?, ?)",
            ("testrepo", str(repo_dir), json.dumps([{"name": "default"}])),
        )
        repo_id = cur.lastrowid

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)

    # Create a scan_run to attach findings to.
    app = build_test_app(tmp_path, _HANDSHAKE, port=_TEST_PORT)

    project_id = app.state.project_registry.register(_PROJECT_NAME, str(tmp_path))

    scan_run_id = run_repo.create(
        project_id=project_id,
        repo_ids=["testrepo"],
        tool_ids=[],
        domains=["code"],
        skip_enrichment=False,
        status="done",
    )

    finding = {**_SAST_FINDING, "repo_id": repo_id}
    finding_repo.insert_findings(scan_run_id, normalize_test_findings([finding]))

    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    finding_id: int = row["id"]

    # Register a stub semgrep tool so the runner's tool lookup succeeds.
    stub_tool = MagicMock()
    stub_tool.name = "semgrep"
    stub_tool.skip = False
    stub_tool.scan_segment = "sast"
    app.state.tool_registry.register(stub_tool)

    # Wire up the event bus so the triage sink can publish.
    bus = EventBus()
    await bus.register_job("triage", "triage")
    await bus.register_job("finding", "finding")
    await bus.register_job("scan", "scan")
    await bus.register_job("report", "report")
    await bus.register_job("report_draft", "report_draft")
    await bus.register_job("chat", "chat")
    app.state.event_bus = bus

    kb_mock = MagicMock()
    kb_mock.get.return_value = [{"id": "doc-1", "metadata": {}}]
    app.state.knowledge_base_cache = {_PROJECT_NAME: kb_mock}

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
            "scan_run_id": scan_run_id,
            "finding_id": finding_id,
        }


@pytest.fixture(autouse=True)
def _reset_triage_singletons():
    """Reset process-wide triage state between tests."""
    from application.locking import get_registry
    from application.triage.run_registry import get_triage_run_registry

    get_triage_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("triage") is not None:  # type: ignore[attr-defined]
        reg._jobs["triage"] = None  # type: ignore[attr-defined,index]
    yield
    get_triage_run_registry().reset()
    if reg._jobs.get("triage") is not None:  # type: ignore[attr-defined]
        reg._jobs["triage"] = None  # type: ignore[attr-defined,index]


class TestBackgroundSdkAutoFailover:
    @pytest.mark.asyncio
    async def test_rate_limit_plan_triggers_api_failover(
        self, background_triage_env
    ) -> None:
        env = background_triage_env
        client: httpx.AsyncClient = env["client"]
        factory: ConnectionFactory = env["factory"]
        project_id: int = env["project_id"]
        scan_run_id: int = env["scan_run_id"]
        finding_id: int = env["finding_id"]

        controller = FakeSdkController()
        controller.on_call(1).raise_rate_limit_plan()
        controller.on_call(2).return_valid_verdict(finding_id)

        with controller.active():
            resp = await client.post(
                f"/api/v1/projects/{project_id}/triage",
                json={
                    "acknowledge_injection_risk": True,
                    "interaction_mode": "background",
                },
                headers=env["mut_headers"],
            )
            assert resp.status_code == 202, resp.text

            rows = _wait_for_executions(
                factory, scan_run_id, expect_count=2, timeout=30.0
            )

        pools = [r["usage_pool"] for r in rows]
        statuses = [r["status"] for r in rows]
        assert pools == ["plan", "api"], f"unexpected pools: {pools}"
        assert statuses == ["rate_limited", "completed"], (
            f"unexpected statuses: {statuses}"
        )
        assert len(controller.calls) == 2
        assert controller.calls[0]["billing_method"] == "plan"
        assert controller.calls[1]["billing_method"] == "api"

        # The failover must actually land a verdict on the finding.
        with factory.connect() as conn:
            finding_row = conn.execute(
                "SELECT confidence FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        assert finding_row is not None, "finding row disappeared"
        assert finding_row["confidence"] == "potential", (
            f"expected verdict 'potential', got {finding_row['confidence']!r}"
        )

"""Shared fixtures for web API tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from application.tools.registry import ToolRegistry

import httpx
import pytest_asyncio

from infrastructure.events.bus import EventBus
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests._app_factory import build_test_app
from tests.finding_helpers import normalize_test_findings


def _seed_global_config(base_path: Path) -> None:
    """Write minimal config files so bootstrap and tool discovery work."""
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
            }
        )
    )


def _seed_commands_config(base_path: Path) -> None:
    """Register gitleaks deterministically so tool-name validation is stable.

    Bootstrap reconciles the tool registry against the host PATH, so a local
    tool is only registered when its binary is installed. This bucket-2 suite
    must not depend on installed CLI binaries. A docker-location entry survives
    reconciliation regardless of PATH, and the run route re-discovers tools
    from this same file, so gitleaks stays registered on both paths.
    """
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "gitleaks": {
                    "type": "repo",
                    "location": "docker",
                    "container": {
                        "name": "tally-test-gitleaks",
                        "tool_path": "/usr/bin/gitleaks",
                    },
                }
            }
        )
    )


def _seed_test_tools(base_path: Path, tool_registry: ToolRegistry) -> None:
    """Re-run tool discovery after app construction."""
    from application.tools.registry import discover_tools

    discover_tools(tool_registry, str(base_path))


TEST_PORT = 12345
HANDSHAKE = "test-handshake-abc123xyz"

_BASE_FINDING: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "url": "https://original.com/path",
    "file_path": "src/app.py",
    "rule_id": "python.flask.sqli",
    "description": "SQL injection risk",
    "segment": "sast",
    "repo": "test-repo",
    "type_secret": True,
    "type_vulnerability": False,
    "profile": "test_project",
    "remediation": "old",
    "author": "jdoe",
    "commit": "abc123",
}


async def _authenticate(client: httpx.AsyncClient) -> dict[str, str]:
    """Exchange handshake for session cookies. Returns mutating-request headers."""
    resp = await client.post(
        "/api/v1/auth/exchange",
        json={"token": HANDSHAKE},
        headers={"origin": f"https://127.0.0.1:{TEST_PORT}"},
    )
    assert resp.status_code == 200, f"exchange failed: {resp.text}"
    # httpx stores Secure cookies in the jar but won't send them over plain
    # HTTP. Delete the auto-stored domain-specific entry, then inject a
    # domain-less copy that bypasses the Secure-flag enforcement.
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    csrf_token = client.cookies["tally_csrf"]
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": f"https://127.0.0.1:{TEST_PORT}",
    }


@pytest_asyncio.fixture()
async def app_client(tmp_path: Path):
    """Yield (client, finding_id, rag_mock, factory, mut_headers, project_id)."""
    _seed_global_config(tmp_path)
    _seed_commands_config(tmp_path)
    # DB must live at the canonical path the registry resolves to.
    db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings([_BASE_FINDING]))

    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    finding_id: int = row["id"]

    kb_mock = MagicMock()
    kb_mock.get.return_value = [{"id": "doc-1", "metadata": {}}]

    app = build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)
    _seed_test_tools(tmp_path, app.state.tool_registry)
    # Seed the per-project knowledge base cache so chroma sync uses the mock.
    app.state.knowledge_base_cache = {"testproject": kb_mock}

    _bus = EventBus()
    await _bus.register_job("finding", "finding")
    await _bus.register_job("scan", "scan")
    await _bus.register_job("triage", "triage")
    await _bus.register_job("report", "report")
    await _bus.register_job("report_draft", "report_draft")
    await _bus.register_job("chat", "chat")
    app.state.event_bus = _bus

    # Seed the registry so project-scoped endpoints can resolve "testproject".
    project_id = app.state.project_registry.register("testproject", str(tmp_path))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"https://127.0.0.1:{TEST_PORT}",
    ) as client:
        mut_headers = await _authenticate(client)
        yield client, finding_id, kb_mock, factory, mut_headers, project_id

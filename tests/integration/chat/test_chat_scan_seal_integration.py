"""Integration test: sealing fires on scan completion.

Drives ``ScanOrchestrator._run()`` directly with a no-op body so the
chat sealing call site is exercised end-to-end without spinning up a
real scan pipeline. Asserts active sessions become expired and that a
follow-up POST to ``.../messages`` returns ``409 CHAT_SESSION_EXPIRED``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest


def _seed_global_config(base_path: Path) -> None:
    """Write a minimal <base>/config/global.json. Required by ConfigManager."""
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "model": "test-model",
                    "host": "http://localhost:11434",
                },
                "ollama_embedding": {
                    "model": "test-embed",
                    "host": "http://localhost:11434",
                },
            }
        )
    )


_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.tools.executor import ToolExecutor  # noqa: E402
from application.tools.orchestrator import ScanOrchestrator  # noqa: E402
from application.tools.registry import ToolRegistry  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402
from domain.pipeline.events import EventBus  # noqa: E402
from domain.tools.scan_types import ScanSummary  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.chat_sessions import (  # noqa: E402
    ChatSessionRepository,
)
from web.adapters.chat_run_registry import get_chat_run_registry  # noqa: E402
from web.server import create_app  # noqa: E402

pytestmark = pytest.mark.integration


def _empty_summary() -> ScanSummary:
    return ScanSummary(
        total_tools_run=0,
        total_tools_skipped=0,
        total_tools_failed=0,
        results=[],
        duration_seconds=0.0,
        findings_ingested=0,
        findings_by_tool={},
    )


def _build_orchestrator(
    *,
    project_id: int,
    tmp_path: Path,
    factory: ConnectionFactory,
    project_name: str = "testproject",
) -> ScanOrchestrator:
    prompt = MagicMock()
    executor = ToolExecutor(
        project_name=project_name,
        base_path=tmp_path,
        prompt=prompt,
        subprocess_runner=MagicMock(),
    )
    bus = EventBus()
    return ScanOrchestrator(
        project=project_name,
        tool_registry=ToolRegistry(),
        tool_executor=executor,
        event_bus=bus,
        prompt=prompt,
        project_id=project_id,
        chat_session_repo=ChatSessionRepository(factory),
    )


def _setup_db(tmp_path: Path) -> tuple[ProjectPaths, ConnectionFactory]:
    _seed_global_config(tmp_path)
    paths = ProjectPaths.from_canonical(str(tmp_path), "testproject")
    paths.findings_db.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return paths, factory


def test_orchestrator_seals_active_sessions_on_successful_scan(
    tmp_path: Path,
) -> None:
    """A successful _run() seals every active chat session for the project."""
    project_id = 17
    _, factory = _setup_db(tmp_path)
    repo = ChatSessionRepository(factory)
    s1 = repo.create(project_id=project_id, title="alive-1")
    s2 = repo.create(project_id=project_id, title="alive-2")

    orch = _build_orchestrator(
        project_id=project_id, tmp_path=tmp_path, factory=factory
    )
    summary = orch._run(_empty_summary)
    assert summary is not None  # _run returns the summary

    for sid in (s1, s2):
        row = repo.get(sid)
        assert row is not None
        assert row.expired_at is not None


def test_orchestrator_does_not_seal_other_projects(tmp_path: Path) -> None:
    """Sealing only touches sessions belonging to the scanned project."""
    project_id = 17
    other_id = 18
    _, factory = _setup_db(tmp_path)
    repo = ChatSessionRepository(factory)
    own = repo.create(project_id=project_id, title="own")
    other = repo.create(project_id=other_id, title="other")

    orch = _build_orchestrator(
        project_id=project_id, tmp_path=tmp_path, factory=factory
    )
    orch._run(_empty_summary)

    own_row = repo.get(own)
    assert own_row is not None and own_row.expired_at is not None
    other_row = repo.get(other)
    assert other_row is not None and other_row.expired_at is None


def test_orchestrator_does_not_seal_when_scan_fails(tmp_path: Path) -> None:
    """A failing scan body MUST NOT seal; sealing is success-branch only."""
    project_id = 17
    _, factory = _setup_db(tmp_path)
    repo = ChatSessionRepository(factory)
    sid = repo.create(project_id=project_id, title="kept-on-failure")

    orch = _build_orchestrator(
        project_id=project_id, tmp_path=tmp_path, factory=factory
    )

    def _explode() -> ScanSummary:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        orch._run(_explode)

    row = repo.get(sid)
    assert row is not None
    assert row.expired_at is None


def test_orchestrator_no_op_when_project_id_is_none(tmp_path: Path) -> None:
    """Legacy callers without a project_id must not crash and must not seal."""
    _, factory = _setup_db(tmp_path)
    repo = ChatSessionRepository(factory)
    sid = repo.create(project_id=99, title="orphan")

    prompt = MagicMock()
    executor = ToolExecutor(
        project_name="testproject",
        base_path=tmp_path,
        prompt=prompt,
        subprocess_runner=MagicMock(),
    )
    bus = EventBus()
    orch = ScanOrchestrator(
        project="testproject",
        tool_registry=ToolRegistry(),
        tool_executor=executor,
        event_bus=bus,
        prompt=prompt,
        project_id=None,
    )
    orch._run(_empty_summary)

    row = repo.get(sid)
    assert row is not None
    assert row.expired_at is None


# End-to-end through the web API


HANDSHAKE = "test-handshake-abc123xyz"


async def _authenticate(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/exchange",
        json={"token": HANDSHAKE},
        headers={"origin": "http://127.0.0.1:12345"},
    )
    assert resp.status_code == 200, resp.text
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    csrf_token = client.cookies["tally_csrf"]
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": "http://127.0.0.1:12345",
    }


@pytest.mark.asyncio
async def test_post_message_after_seal_returns_409(tmp_path: Path) -> None:
    """After sealing, POST to a sealed session returns 409 CHAT_SESSION_EXPIRED."""
    get_chat_run_registry().reset()
    _, factory = _setup_db(tmp_path)

    app = create_app(str(tmp_path), HANDSHAKE, port=12345)
    project_id = app.state.project_registry.register("testproject", str(tmp_path))

    repo = ChatSessionRepository(factory)
    sid = repo.create(project_id=project_id, title="will-seal")

    orch = _build_orchestrator(
        project_id=project_id, tmp_path=tmp_path, factory=factory
    )
    orch._run(_empty_summary)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:12345"
    ) as client:
        mut_headers = await _authenticate(client)
        resp = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
            json={"content": "after seal"},
            headers=mut_headers,
        )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "CHAT_SESSION_EXPIRED"

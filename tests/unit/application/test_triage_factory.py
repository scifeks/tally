"""Tests triage composition."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.ports.triage_agent import TriageBackendFactoryPort
from application.triage.factory import (
    TriageAgentFactory,
    TriageProviderNotConfiguredError,
    build_triage_runner,
    ensure_triage_backend_configured,
    load_triage_provider,
)


class _StubAgentFactory(TriageBackendFactoryPort):
    def __init__(self, agent) -> None:
        self.agent = agent
        self.calls = 0

    def create(self):
        self.calls += 1
        return self.agent


def test_triage_agent_factory_builds_claude_agent() -> None:
    with (
        patch(
            "application.triage.factory.load_triage_provider",
            return_value="claude_code",
        ),
        patch(
            "infrastructure.agents.claude_triage_agent.ClaudeTriageAgent"
        ) as mock_agent,
    ):
        factory = TriageAgentFactory()

        agent = factory.create()

    assert agent is mock_agent.return_value
    mock_agent.assert_called_once_with()


def test_triage_agent_factory_builds_opencode_agent() -> None:
    with (
        patch(
            "application.triage.factory.load_triage_provider",
            return_value="open_code",
        ),
        patch(
            "infrastructure.agents.opencode_triage_agent.OpenCodeTriageAgent"
        ) as mock_agent,
    ):
        factory = TriageAgentFactory()

        agent = factory.create()

    assert agent is mock_agent.return_value
    mock_agent.assert_called_once_with()


def test_load_triage_provider_reads_global_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps({"triage_agent_provider": "claude_code"})
    )

    assert load_triage_provider(app_root=tmp_path) == "claude_code"


def test_ensure_triage_backend_configured_raises_when_disabled(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(json.dumps({}))

    with pytest.raises(TriageProviderNotConfiguredError, match="Triage is disabled"):
        ensure_triage_backend_configured(app_root=tmp_path)


def test_ensure_triage_backend_configured_accepts_open_code(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps({"triage_agent_provider": "open_code"})
    )

    assert ensure_triage_backend_configured(app_root=tmp_path) == "open_code"


def test_build_triage_runner_uses_factory_agent(tmp_path: Path) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True, exist_ok=True)
    findings_db.touch()

    agent = MagicMock()
    agent_factory = _StubAgentFactory(agent)
    tool_registry = MagicMock()

    with (
        patch("application.triage.factory.make_store") as mock_make_store,
        patch("application.triage.factory.load_mcp_defaults", return_value=(1, 2, 300)),
    ):
        repos = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_make_store.return_value = repos

        runner = build_triage_runner(
            "proj",
            tool_registry,
            app_root=tmp_path,
            triage_agent_factory=agent_factory,
        )

    assert runner._triage_backend is agent
    assert runner._session_timeout_seconds == 300
    assert runner._tool_registry is tool_registry
    assert agent_factory.calls == 1


def test_build_triage_runner_resets_for_resume_before_running(tmp_path: Path) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True, exist_ok=True)
    findings_db.touch()

    agent = MagicMock()
    agent_factory = _StubAgentFactory(agent)
    triage_repo = MagicMock()

    with (
        patch("application.triage.factory.make_store") as mock_make_store,
        patch("application.triage.factory.load_mcp_defaults", return_value=(1, 2, 300)),
    ):
        mock_make_store.return_value = (
            MagicMock(),
            MagicMock(),
            triage_repo,
            MagicMock(),
        )

        build_triage_runner(
            "proj",
            MagicMock(),
            app_root=tmp_path,
            reset_for_resume_scan_run_id=17,
            triage_agent_factory=agent_factory,
        )

    triage_repo.reset_for_resume.assert_called_once_with(17)


def test_build_triage_runner_raises_when_project_db_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Project database not found"):
        build_triage_runner("proj", MagicMock(), app_root=tmp_path)

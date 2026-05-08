"""Tests triage composition."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.factory import (
    TriageAgentFactory,
    TriageProviderNotConfiguredError,
    build_triage_runner,
    ensure_triage_backend_configured,
    load_triage_provider,
)


def test_triage_agent_factory_builds_claude_agent() -> None:
    mock_cfg = MagicMock()
    mock_cfg.global_config.claude = None

    with (
        patch(
            "application.triage.factory.load_triage_provider",
            return_value="claude_code",
        ),
        patch(
            "application.triage.factory.ConfigManager",
            return_value=mock_cfg,
        ),
        patch(
            "infrastructure.agents.claude_triage_agent.ClaudeTriageAgent"
        ) as mock_agent,
    ):
        factory = TriageAgentFactory(app_root=Path("/unused"))

        agent = factory.create()

    assert agent is mock_agent.return_value
    mock_agent.assert_called_once_with(model="sonnet")


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
        factory = TriageAgentFactory(app_root=Path("/unused"))

        agent = factory.create()

    assert agent is mock_agent.return_value
    mock_agent.assert_called_once_with()


def test_load_triage_provider_reads_global_config(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps({"triage_agent_provider": "claude_code"})
    )

    assert load_triage_provider(app_root=tmp_path) == "claude_code"


def test_ensure_triage_backend_configured_raises_when_disabled(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(json.dumps({}))

    with pytest.raises(
        TriageProviderNotConfiguredError,
        match="Triage is disabled",
    ):
        ensure_triage_backend_configured(app_root=tmp_path)


def test_ensure_triage_backend_configured_accepts_open_code(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps({"triage_agent_provider": "open_code"})
    )

    assert ensure_triage_backend_configured(app_root=tmp_path) == "open_code"


def _mock_repo_repository() -> MagicMock:
    """Return a mock RepositoryRepository with empty list_active."""
    mock = MagicMock()
    mock.list_active.return_value = []
    return mock


def test_build_triage_runner_uses_factory_agent(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True, exist_ok=True)
    findings_db.touch()
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text("{}")

    agent = MagicMock()
    tool_registry = MagicMock()

    with (
        patch("application.triage.factory.make_store") as mock_make_store,
        patch("application.triage.factory.TriageAgentFactory") as mock_factory_cls,
        patch(
            "application.triage.factory.RepositoryRepository",
            return_value=_mock_repo_repository(),
        ),
        patch(
            "application.triage.factory.load_triage_provider",
            return_value="claude_code",
        ),
    ):
        mock_make_store.return_value = (
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        mock_factory_cls.return_value.create.return_value = agent

        runner = build_triage_runner(
            "proj",
            tool_registry,
            app_root=tmp_path,
        )

    assert runner._triage_backend is agent
    assert runner._session_timeout_seconds == 300
    assert runner._tool_registry is tool_registry
    assert runner._triaged_by == "claudecode"
    mock_factory_cls.assert_called_once_with(app_root=tmp_path)


def test_build_triage_runner_wires_finding_repo(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True, exist_ok=True)
    findings_db.touch()
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text("{}")

    finding_repo = MagicMock()

    with (
        patch("application.triage.factory.make_store") as mock_make_store,
        patch("application.triage.factory.TriageAgentFactory"),
        patch(
            "application.triage.factory.RepositoryRepository",
            return_value=_mock_repo_repository(),
        ),
        patch(
            "application.triage.factory.load_triage_provider",
            return_value="claude_code",
        ),
    ):
        mock_make_store.return_value = (
            MagicMock(),
            finding_repo,
            MagicMock(),
            MagicMock(),
        )

        runner = build_triage_runner(
            "proj",
            MagicMock(),
            app_root=tmp_path,
        )

    assert runner._finding_repo is finding_repo


def test_build_triage_runner_resets_for_resume_before_running(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True, exist_ok=True)
    findings_db.touch()
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text("{}")

    triage_repo = MagicMock()

    with (
        patch("application.triage.factory.make_store") as mock_make_store,
        patch("application.triage.factory.TriageAgentFactory"),
        patch(
            "application.triage.factory.RepositoryRepository",
            return_value=_mock_repo_repository(),
        ),
        patch(
            "application.triage.factory.load_triage_provider",
            return_value="claude_code",
        ),
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
        )

    triage_repo.reset_for_resume.assert_called_once_with(17)


def test_build_triage_runner_raises_when_project_db_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="Project database not found"):
        build_triage_runner("proj", MagicMock(), app_root=tmp_path)

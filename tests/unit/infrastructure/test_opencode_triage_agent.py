"""Tests OpenCode one-shot session prep."""

from __future__ import annotations

from pathlib import Path

from infrastructure.agents.opencode_triage_agent import OpenCodeTriageAgent


def test_prepare_session_yields_app_root_as_cwd(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path) as session:
        assert session.cwd == tmp_path


def test_prepare_session_does_not_create_config(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        assert not any(tmp_path.iterdir())

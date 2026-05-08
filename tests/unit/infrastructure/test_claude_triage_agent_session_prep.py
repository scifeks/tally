"""Tests Claude one-shot session prep."""

from __future__ import annotations

from pathlib import Path

from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent


def test_prepare_session_yields_app_root_as_cwd(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model="sonnet", compose_path=tmp_path / "compose.yaml")

    with agent.prepare_session(
        project="test-project", run_id=42, app_root=tmp_path
    ) as prepared:
        assert prepared.cwd == tmp_path


def test_prepare_session_does_not_write_mcp_json(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model="sonnet", compose_path=tmp_path / "compose.yaml")

    with agent.prepare_session(project="test-project", run_id=42, app_root=tmp_path):
        assert not (tmp_path / ".mcp.json").exists()

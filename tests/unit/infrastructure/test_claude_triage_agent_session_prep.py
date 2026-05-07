"""Tests Claude session prep."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent


def test_prepare_session_writes_mcp_json_file(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="test-project", run_id=42, app_root=tmp_path):
        assert (tmp_path / ".mcp.json").exists()


def test_prepare_session_removes_mcp_json_after_exit(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="test-project", run_id=42, app_root=tmp_path):
        pass

    assert not (tmp_path / ".mcp.json").exists()


def test_prepare_session_returns_app_root_as_cwd(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()

    with agent.prepare_session(
        project="test-project", run_id=42, app_root=tmp_path
    ) as prepared:
        assert prepared.cwd == tmp_path


def test_prepare_session_mcp_json_contains_project_name(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="test-project", run_id=42, app_root=tmp_path):
        data = json.loads((tmp_path / ".mcp.json").read_text())

    assert "test-project" in data["mcpServers"]["tally-mcp"]["args"]


def test_prepare_session_mcp_json_structure(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="test-project", run_id=42, app_root=tmp_path):
        data = json.loads((tmp_path / ".mcp.json").read_text())

    assert data["mcpServers"]["tally-mcp"]["type"] == "stdio"
    assert data["mcpServers"]["tally-mcp"]["command"] == sys.executable


def test_prepare_session_mcp_json_contains_run_id_env(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="test-project", run_id=42, app_root=tmp_path):
        data = json.loads((tmp_path / ".mcp.json").read_text())

    env = data["mcpServers"]["tally-mcp"]["env"]
    assert env["TALLY_TRIAGE_RUN_ID"] == "42"
    assert env["TALLY_TRIAGED_BY"] == "claudecode"

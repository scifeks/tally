"""Unit tests for OpenCodeTriageAgent session preparation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.agents.opencode_triage_agent import OpenCodeTriageAgent


def test_prepare_session_yields_app_root_as_cwd(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path) as session:
        assert session.cwd == tmp_path


def test_prepare_session_sets_opencode_config_env(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        assert agent._session_env is not None
        config_path = Path(agent._session_env["OPENCODE_CONFIG"])
        assert config_path.exists()
        assert config_path.name == "opencode.json"


def test_prepare_session_removes_generated_config_after_exit(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        assert agent._session_env is not None
        config_path = Path(agent._session_env["OPENCODE_CONFIG"])

    assert agent._session_env is None
    assert not config_path.exists()


def test_prepare_session_cleans_up_generated_config_on_exception(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent()

    with pytest.raises(RuntimeError, match="boom"):
        with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
            assert agent._session_env is not None
            config_path = Path(agent._session_env["OPENCODE_CONFIG"])
            raise RuntimeError("boom")

    assert agent._session_env is None
    assert not config_path.exists()


def test_prepare_session_writes_mcp_config_payload(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        assert agent._session_env is not None
        config_path = Path(agent._session_env["OPENCODE_CONFIG"])
        payload = json.loads(config_path.read_text())

    server = payload["mcp"]["tally-mcp"]
    permission = payload["permission"]
    assert payload["$schema"] == "https://opencode.ai/config.json"
    assert server["type"] == "local"
    assert server["enabled"] is True
    assert server["command"] == [
        sys.executable,
        "-m",
        "tally_mcp.server",
        "--project",
        "proj",
    ]
    assert server["environment"]["TALLY_TRIAGE_RUN_ID"] == "42"
    assert server["environment"]["TALLY_TRIAGED_BY"] == "opencode"
    assert permission["edit"] == "deny"
    assert permission["bash"] == {"*": "deny"}
    assert permission["webfetch"] == "deny"
    assert permission["tally-mcp_get_findings_batch"] == "allow"
    assert permission["tally-mcp_update_findings_batch"] == "allow"
    assert permission["tally-mcp_*"] == "deny"
    assert permission["read"] == {"*": "allow"}
    assert permission["write"] == {"*": "deny"}


def test_prepare_session_does_not_use_mcp_wildcard_allow(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        assert agent._session_env is not None
        config_path = Path(agent._session_env["OPENCODE_CONFIG"])
        payload = json.loads(config_path.read_text())

    assert payload["permission"]["tally-mcp_*"] != "allow"


def test_build_run_command_passes_dangerously_skip_permissions(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent()

    command = agent._build_run_command(cwd=tmp_path)

    assert "--dangerously-skip-permissions" in command


def test_run_session_merges_opencode_config_into_subprocess_env(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        with patch("subprocess.run") as mock_run:
            agent.run_session(
                "prompt",
                timeout_seconds=30,
                cwd=tmp_path,
            )

    env = mock_run.call_args.kwargs["env"]
    assert "OPENCODE_CONFIG" in env
    assert env["OPENCODE_CONFIG"].endswith("opencode.json")


def test_build_run_command_uses_dir_and_json_format(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    command = agent._build_run_command(cwd=tmp_path)

    assert command == [
        "opencode",
        "run",
        "--dangerously-skip-permissions",
        "--dir",
        str(tmp_path),
        "--format",
        "json",
    ]

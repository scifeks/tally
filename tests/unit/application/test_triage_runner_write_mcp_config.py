"""Unit tests for TriageRunner._write_mcp_config."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.triage.runner import TriageRunner


def _make_runner(tmp_path: Path) -> TriageRunner:
    return TriageRunner(
        project="test-project",
        run_repo=MagicMock(),
        triage_repo=MagicMock(),
        audit_repo=MagicMock(),
        app_root=tmp_path,
    )


def _create_venv_python(tmp_path: Path) -> Path:
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    return venv_python


class TestTriageRunnerWriteMcpConfig:
    def test_writes_mcp_json_file(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        _create_venv_python(tmp_path)

        runner._write_mcp_config(42)

        assert (tmp_path / ".mcp.json").exists()

    def test_returns_mcp_json_path(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        _create_venv_python(tmp_path)

        result = runner._write_mcp_config(42)

        assert result == tmp_path / ".mcp.json"

    def test_mcp_json_contains_project_name(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        _create_venv_python(tmp_path)

        runner._write_mcp_config(42)

        data = json.loads((tmp_path / ".mcp.json").read_text())
        assert "test-project" in data["mcpServers"]["tally-mcp"]["args"]

    def test_mcp_json_structure(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        venv_python = _create_venv_python(tmp_path)

        runner._write_mcp_config(42)

        data = json.loads((tmp_path / ".mcp.json").read_text())
        assert data["mcpServers"]["tally-mcp"]["type"] == "stdio"
        assert data["mcpServers"]["tally-mcp"]["command"] == str(venv_python)

    def test_mcp_json_contains_run_id_env(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        _create_venv_python(tmp_path)

        runner._write_mcp_config(42)

        data = json.loads((tmp_path / ".mcp.json").read_text())
        env = data["mcpServers"]["tally-mcp"]["env"]
        assert env["TALLY_TRIAGE_RUN_ID"] == "42"

    def test_raises_runtime_error_if_venv_python_missing(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)

        with pytest.raises(RuntimeError, match="Venv Python not found"):
            runner._write_mcp_config(42)

"""Unit tests for _build_raw_command."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.tools.scan_types.execution import _build_raw_command


class TestBuildRawCommand:
    def test_docker_location_with_container(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(name="tally-zap", tool_path="/usr/bin/zap.sh"),
        )
        cli_args = ["--target", "http://localhost:8080"]
        result = _build_raw_command("zap", docker_config, cli_args)
        assert result[0:4] == ["docker", "exec", "tally-zap", "/usr/bin/zap.sh"]
        assert result[4:] == ["--target", "http://localhost:8080"]

    def test_docker_exec_without_args(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(name="gitleaks", tool_path="/usr/bin/gitleaks"),
        )
        cli_args: list[str] = []
        result = _build_raw_command("gitleaks", docker_config, cli_args)
        assert result == ["docker", "exec", "gitleaks", "/usr/bin/gitleaks"]

    def test_docker_exec_multiple_args(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(
                name="semgrep",
                tool_path="/usr/bin/semgrep",
            ),
        )
        cli_args = ["scan", "--config", "p/security-audit", "--json"]
        result = _build_raw_command("semgrep", docker_config, cli_args)
        assert result == [
            "docker",
            "exec",
            "semgrep",
            "/usr/bin/semgrep",
            "scan",
            "--config",
            "p/security-audit",
            "--json",
        ]

    def test_local_location_with_path(self) -> None:
        local_config = SimpleNamespace(location="local", path="/usr/bin/gitleaks")
        cli_args = ["detect", "--source", "/repo"]
        result = _build_raw_command("gitleaks", local_config, cli_args)
        assert result == ["/usr/bin/gitleaks", "detect", "--source", "/repo"]

    def test_local_location_without_args(self) -> None:
        local_config = SimpleNamespace(location="local", path="/bin/echo")
        cli_args: list[str] = []
        result = _build_raw_command("echo", local_config, cli_args)
        assert result == ["/bin/echo"]

    def test_config_location_is_none(self) -> None:
        config = SimpleNamespace(location=None)
        with pytest.raises(ValueError, match="unknown location"):
            _build_raw_command("test_tool", config, [])

    def test_unknown_location(self) -> None:
        config = SimpleNamespace(location="cloud")
        with pytest.raises(ValueError, match="unknown location"):
            _build_raw_command("test_tool", config, [])

    def test_docker_missing_container_attribute(self) -> None:
        docker_config = SimpleNamespace(location="docker")
        with pytest.raises(ValueError, match="docker location requires"):
            _build_raw_command("zap", docker_config, [])

    def test_docker_container_missing_name(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(tool_path="/usr/bin/zap.sh"),
        )
        with pytest.raises(ValueError, match="container missing name or tool_path"):
            _build_raw_command("zap", docker_config, [])

    def test_docker_container_missing_tool_path(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(name="tally-zap"),
        )
        with pytest.raises(ValueError, match="container missing name or tool_path"):
            _build_raw_command("zap", docker_config, [])

    def test_docker_container_name_empty_string(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(name="", tool_path="/usr/bin/zap.sh"),
        )
        with pytest.raises(ValueError, match="container missing name or tool_path"):
            _build_raw_command("zap", docker_config, [])

    def test_docker_container_tool_path_empty_string(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(name="tally-zap", tool_path=""),
        )
        with pytest.raises(ValueError, match="container missing name or tool_path"):
            _build_raw_command("zap", docker_config, [])

    def test_local_missing_path_attribute(self) -> None:
        local_config = SimpleNamespace(location="local")
        with pytest.raises(ValueError, match="local location requires path"):
            _build_raw_command("gitleaks", local_config, [])

    def test_local_path_is_empty_string(self) -> None:
        local_config = SimpleNamespace(location="local", path="")
        with pytest.raises(ValueError, match="local location requires path"):
            _build_raw_command("gitleaks", local_config, [])

    def test_docker_preserves_cli_args_exactly(self) -> None:
        docker_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(
                name="my-container",
                tool_path="/app/tool",
            ),
        )
        cli_args = ["--flag", "value with spaces", "--another", "123"]
        result = _build_raw_command("tool", docker_config, cli_args)
        assert result[-4:] == cli_args

"""Unit tests for XSSTrikeDockerTool.build_command and build_execution_passes."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from domain.tools.execution_config import ToolExecutionConfig
from infrastructure.tools.wrappers.docker.xsstrike import XSSTrikeDockerTool
from infrastructure.tools.wrappers.local.xsstrike import _recommended_thread_count

_JIT_PATCH_TARGET = "application.url_inventory.jit.jit_rebuild_artifacts"


def _make_config(
    container_name: str = "xsstrike", tool_path: str = "/xsstrike.py"
) -> Any:
    return SimpleNamespace(
        container=SimpleNamespace(name=container_name, tool_path=tool_path)
    )


def _make_tool(
    container_name: str = "xsstrike", tool_path: str = "/xsstrike.py"
) -> XSSTrikeDockerTool:
    return XSSTrikeDockerTool(_make_config(container_name, tool_path))


def _make_repo(**kwargs: Any) -> MagicMock:
    repo = MagicMock()
    repo.name = kwargs.get("name", "myrepo")
    repo.uuid = kwargs.get("uuid", "00000000-0000-0000-0000-000000000001")
    repo.xsstrike_crawl_level = kwargs.get("xsstrike_crawl_level", 10)
    repo.xsstrike_headers = kwargs.get("xsstrike_headers", None)
    service = MagicMock()
    service.base_urls = kwargs.get("base_urls", ["http://localhost:8080"])
    service.docker_path = ""
    service.container_name = ""
    service.relative_path = ""
    service.dependencies_file = ""
    service.crawl_enabled = True
    service.type = []
    service.test_dirs = []
    service.ignore_dirs = []
    repo.services = [service]
    return repo


def _tool_config(
    blind_xss_callback_url: str = "",
) -> ToolExecutionConfig:
    return ToolExecutionConfig(
        noir_provider=None,
        blind_xss_callback_url=blind_xss_callback_url,
    )


# build_command: basic flag assertions


class TestDockerBuildCommandFlags:
    def test_path_flag_not_present(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "--path" not in cmd

    def test_threads_flag_present(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "-t" in cmd

    def test_threads_value_in_safe_range(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        idx = cmd.index("-t")
        assert 2 <= int(cmd[idx + 1]) <= 8

    def test_threads_value_equals_recommended(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        idx = cmd.index("-t")
        assert int(cmd[idx + 1]) == _recommended_thread_count()

    def test_timeout_flag_present(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "--timeout" in cmd

    def test_timeout_value_is_15(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        idx = cmd.index("--timeout")
        assert cmd[idx + 1] == "15"

    def test_console_log_level_not_file_log(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "--console-log-level" in cmd
        assert "--log-file" not in cmd
        assert "--file-log-level" not in cmd

    def test_console_log_level_value_is_debug(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        idx = cmd.index("--console-log-level")
        assert cmd[idx + 1] == "DEBUG"

    def test_new_flags_present_in_seeds_mode(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(seeds_file="/tally_data/seeds.txt")
        assert "--path" not in cmd
        assert "-t" in cmd
        assert "--timeout" in cmd

    def test_blind_flag_when_enabled(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080", blind=True)
        assert "--blind" in cmd

    def test_no_blind_flag_by_default(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "--blind" not in cmd

    def test_crawl_level_propagated(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080", crawl_level=5)
        idx = cmd.index("-l")
        assert cmd[idx + 1] == "5"

    def test_default_crawl_level_is_10(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        idx = cmd.index("-l")
        assert cmd[idx + 1] == "10"

    def test_headers_serialized_as_json(self) -> None:
        tool = _make_tool()
        hdrs = {"Authorization": "Bearer tok", "X-Custom": "val"}
        cmd = tool.build_command(base_url="http://localhost:8080", headers=hdrs)
        assert "--headers" in cmd
        idx = cmd.index("--headers")
        assert json.loads(cmd[idx + 1]) == hdrs

    def test_no_headers_flag_when_headers_none(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "--headers" not in cmd

    def test_seeds_flag_used_when_seeds_file_given(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(seeds_file="/tally_data/seeds.txt")
        assert "--seeds" in cmd
        assert "-u" not in cmd

    def test_u_flag_used_when_base_url_given(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert "-u" in cmd
        assert "--seeds" not in cmd

    def test_raises_when_neither_url_nor_seeds(self) -> None:
        tool = _make_tool()
        with pytest.raises(ValueError, match="base_url or seeds_file"):
            tool.build_command()

    def test_docker_exec_prefix(self) -> None:
        tool = _make_tool(container_name="xsstrike-ctr", tool_path="/opt/xsstrike.py")
        cmd = tool.build_command(base_url="http://localhost:8080")
        assert cmd[:2] == ["docker", "exec"]
        assert "xsstrike-ctr" in cmd
        assert "/opt/xsstrike.py" in cmd


# build_execution_passes: config parity with local wrapper


class TestDockerBuildExecutionPasses:
    """Phase 9: the seeds path comes from ``jit_rebuild_artifacts`` (which
    rebuilds it from ``url_findings`` rows). These tests stub the helper
    to isolate the docker wrapper's pass-construction logic."""

    def _make_context(
        self,
        repo: MagicMock,
        tmp_path: Any,
        blind_url: str = "",
    ) -> MagicMock:
        ctx = MagicMock(spec=["repo", "base_path", "project_name", "tool_config"])
        ctx.repo = repo
        ctx.base_path = str(tmp_path)
        ctx.project_name = "proj"
        ctx.tool_config = _tool_config(blind_url)
        return ctx

    def _make_seeds(self, tmp_path: Any, name: str = "seeds.txt") -> str:
        seeds = tmp_path / name
        seeds.write_text("http://target/path\n")
        return str(seeds)

    def _patched(self, seeds: str | None = None, oas3: str | None = None):
        return patch(_JIT_PATCH_TARGET, return_value=(seeds, oas3))

    def test_skips_when_jit_returns_no_seeds(self, tmp_path: Any) -> None:
        tool = _make_tool()
        repo = _make_repo()
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=None):
            passes = tool.build_execution_passes(ctx)
        assert passes == []

    def test_returns_one_pass_when_seeds_exist(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo()
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1

    def test_seeds_file_passed_as_kwarg(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo()
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["seeds_file"] == seeds

    def test_crawl_level_honored(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo(xsstrike_crawl_level=7)
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["crawl_level"] == 7

    def test_headers_honored(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        hdrs = {"Cookie": "session=abc"}
        repo = _make_repo(xsstrike_headers=hdrs)
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["headers"] == hdrs

    def test_no_headers_key_when_headers_none(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo(xsstrike_headers=None)
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert "headers" not in passes[0].kwargs

    def test_pass_label_suffix_is_repo_name(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo(name="myapp")
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert passes[0].label_suffix == "myapp"

    def test_blind_kwarg_set_when_callback_configured(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo()
        ctx = self._make_context(repo, tmp_path, blind_url="https://cb.example.com")
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["blind"] is True

    def test_no_blind_kwarg_when_callback_empty(self, tmp_path: Any) -> None:
        tool = _make_tool()
        seeds = self._make_seeds(tmp_path)
        repo = _make_repo()
        ctx = self._make_context(repo, tmp_path)
        with self._patched(seeds=seeds):
            passes = tool.build_execution_passes(ctx)
        assert "blind" not in passes[0].kwargs

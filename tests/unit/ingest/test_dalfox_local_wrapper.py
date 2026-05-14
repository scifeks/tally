"""Unit tests for DalFoxLocalTool.build_command."""

from __future__ import annotations

from typing import Any

from infrastructure.tools.wrappers.local.dalfox import DalFoxLocalTool


def _make_tool() -> DalFoxLocalTool:
    return DalFoxLocalTool(config=None)


class TestBuildCommandFlags:
    def _base_kwargs(self) -> dict[str, Any]:
        return {
            "seeds_file": "/tmp/seeds.txt",
            "output_file": "/tmp/out.json",
        }

    def test_remote_payloads_always_present(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "--remote-payloads" in cmd
        idx = cmd.index("--remote-payloads")
        assert cmd[idx + 1] == "portswigger,payloadbox"

    def test_deep_domxss_present(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "--deep-domxss" in cmd

    def test_skip_grepping_present(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "--skip-grepping" in cmd

    def test_json_format_and_output_file(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "--format" in cmd
        idx = cmd.index("--format")
        assert cmd[idx + 1] == "json"
        assert "-o" in cmd
        idx = cmd.index("-o")
        assert cmd[idx + 1] == "/tmp/out.json"

    def test_file_subcommand_with_seeds(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "file" in cmd
        assert "/tmp/seeds.txt" in cmd

    def test_url_subcommand_without_seeds(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(
            base_url="http://example.com",
            output_file="/tmp/out.json",
        )
        assert "url" in cmd
        assert "http://example.com" in cmd
        assert "file" not in cmd

    def test_headers_passed_as_h_flags(self) -> None:
        tool = _make_tool()
        kwargs = {
            **self._base_kwargs(),
            "headers": {"Cookie": "s=1", "X-Key": "v"},
        }
        cmd = tool.build_command(**kwargs)
        h_indices = [i for i, v in enumerate(cmd) if v == "-H"]
        assert len(h_indices) == 2

    def test_no_h_flag_when_no_headers(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "-H" not in cmd

    def test_blind_callback_adds_b_flag(self) -> None:
        tool = _make_tool()
        kwargs = {
            **self._base_kwargs(),
            "blind_xss_callback": "https://cb.example.com",
        }
        cmd = tool.build_command(**kwargs)
        assert "-b" in cmd
        idx = cmd.index("-b")
        assert cmd[idx + 1] == "https://cb.example.com"

    def test_no_b_flag_when_no_callback(self) -> None:
        tool = _make_tool()
        cmd = tool.build_command(**self._base_kwargs())
        assert "-b" not in cmd

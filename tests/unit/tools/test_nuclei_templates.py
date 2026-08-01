"""Unit tests for nuclei template handling."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.tools.wrappers.local.nuclei import NucleiLocalTool


class TestEnsureTemplates:
    def test_ensure_templates_downloads_when_missing(self) -> None:
        tool = NucleiLocalTool()
        with patch.object(Path, "is_dir", return_value=False):
            with patch("subprocess.run") as mock_run:
                tool._ensure_templates()
        mock_run.assert_called_once_with(
            ["nuclei", "-update-templates"], check=True, capture_output=True
        )

    def test_ensure_templates_skips_when_present(self) -> None:
        tool = NucleiLocalTool()
        with patch.object(Path, "is_dir", return_value=True):
            with patch("subprocess.run") as mock_run:
                tool._ensure_templates()
        mock_run.assert_not_called()

    def test_ensure_templates_uses_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("NUCLEI_TEMPLATES_DIR", "/custom/templates")
        tool = NucleiLocalTool()

        with patch("pathlib.Path.is_dir", return_value=False):
            with patch("subprocess.run") as mock_run:
                tool._ensure_templates()

        mock_run.assert_called_once_with(
            ["nuclei", "-update-templates"], check=True, capture_output=True
        )

    def test_ensure_templates_uses_custom_nuclei_path(self) -> None:
        config = MagicMock()
        config.path = "/custom/nuclei"
        tool = NucleiLocalTool(config)

        with patch.object(Path, "is_dir", return_value=False):
            with patch("subprocess.run") as mock_run:
                tool._ensure_templates()

        mock_run.assert_called_once_with(
            ["/custom/nuclei", "-update-templates"], check=True, capture_output=True
        )


class TestBuildCommandTemplates:
    def test_build_command_comma_separated_templates(self) -> None:
        tool = NucleiLocalTool()
        cmd = tool.build_command(
            base_url="http://example.com",
            pass_type="automatic",
            output_file="/tmp/out.json",
            custom_template_dir="/repo/.nuclei",
            default_template_dir="/home/user/nuclei-templates",
        )

        t_idx = cmd.index("-t")
        template_str = cmd[t_idx + 1]
        assert "/home/user/nuclei-templates" in template_str
        assert "/repo/.nuclei" in template_str
        assert "," in template_str
        assert template_str == "/home/user/nuclei-templates,/repo/.nuclei"

    def test_build_command_custom_only_no_default(self) -> None:
        tool = NucleiLocalTool()
        cmd = tool.build_command(
            base_url="http://example.com",
            pass_type="automatic",
            output_file="/tmp/out.json",
            custom_template_dir="/repo/.nuclei",
        )

        if "-t" in cmd:
            t_idx = cmd.index("-t")
            template_str = cmd[t_idx + 1]
            assert template_str == "/repo/.nuclei"
        else:
            pytest.fail("Expected -t flag in command")

    def test_build_command_no_templates(self) -> None:
        tool = NucleiLocalTool()
        cmd = tool.build_command(
            base_url="http://example.com",
            pass_type="automatic",
            output_file="/tmp/out.json",
        )

        assert "-t" not in cmd

    def test_build_command_default_only(self) -> None:
        tool = NucleiLocalTool()
        cmd = tool.build_command(
            base_url="http://example.com",
            pass_type="automatic",
            output_file="/tmp/out.json",
            default_template_dir="/home/user/nuclei-templates",
        )

        assert "-t" not in cmd


class TestResolveDefaultTemplatesDir:
    def test_resolve_templates_dir_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            if "NUCLEI_TEMPLATES_DIR" in os.environ:
                del os.environ["NUCLEI_TEMPLATES_DIR"]
            result = NucleiLocalTool._resolve_default_templates_dir()
        assert result == Path.home() / "nuclei-templates"

    def test_resolve_templates_dir_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("NUCLEI_TEMPLATES_DIR", "/custom/path")
        result = NucleiLocalTool._resolve_default_templates_dir()
        assert result == Path("/custom/path")

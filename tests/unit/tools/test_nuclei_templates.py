"""Unit tests for nuclei template auto-download and custom template path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.tools.wrappers.local.nuclei import NucleiLocalTool


class TestNucleiTemplates:
    def _make_tool(self, path: str = "nuclei") -> NucleiLocalTool:
        config = MagicMock()
        config.path = path
        return NucleiLocalTool(config=config)

    def test_ensure_templates_skips_when_dir_exists(self) -> None:
        tool = self._make_tool()
        with (
            patch.object(
                type(tool),
                "_resolve_default_templates_dir",
                return_value=Path("/fake/nuclei-templates"),
            ),
            patch("subprocess.run") as mock_run,
        ):
            with patch.object(Path, "is_dir", return_value=True):
                tool._ensure_templates()
            mock_run.assert_not_called()

    def test_ensure_templates_downloads_when_dir_missing(self) -> None:
        tool = self._make_tool("/usr/bin/nuclei")
        with (
            patch.object(
                type(tool),
                "_resolve_default_templates_dir",
                return_value=Path("/fake/nuclei-templates"),
            ),
            patch("subprocess.run") as mock_run,
        ):
            with patch.object(Path, "is_dir", return_value=False):
                tool._ensure_templates()
            mock_run.assert_called_once_with(
                ["/usr/bin/nuclei", "-update-templates"],
                check=True,
                capture_output=True,
            )

    @pytest.mark.parametrize(
        "env_val,expected",
        [
            (None, Path.home() / "nuclei-templates"),
            (
                "/custom/templates",
                Path("/custom/templates"),
            ),
        ],
        ids=["default", "env-override"],
    )
    def test_resolve_default_templates_dir(
        self, env_val: str | None, expected: Path
    ) -> None:
        with patch.dict(
            "os.environ",
            {"NUCLEI_TEMPLATES_DIR": env_val} if env_val else {},
            clear=False,
        ):
            if env_val is None:
                with patch.dict("os.environ", {}, clear=False):
                    import os

                    os.environ.pop("NUCLEI_TEMPLATES_DIR", None)
                    result = NucleiLocalTool._resolve_default_templates_dir()
            else:
                result = NucleiLocalTool._resolve_default_templates_dir()
        assert result == expected

    def test_build_command_no_custom_templates(self) -> None:
        tool = self._make_tool()
        cmd = tool.build_command(
            base_url="https://example.com",
            pass_type="automatic",
            output_file="/tmp/out.json",
        )
        assert "-t" not in cmd

    def test_build_command_custom_only(self) -> None:
        tool = self._make_tool()
        cmd = tool.build_command(
            base_url="https://example.com",
            pass_type="automatic",
            output_file="/tmp/out.json",
            custom_template_dir="/repo/.nuclei",
        )
        assert "-t" in cmd
        idx = cmd.index("-t")
        assert cmd[idx + 1] == "/repo/.nuclei"

    def test_build_command_both_default_and_custom(self) -> None:
        tool = self._make_tool()
        cmd = tool.build_command(
            base_url="https://example.com",
            pass_type="dast",
            output_file="/tmp/out.json",
            custom_template_dir="/repo/.nuclei",
            default_template_dir="/home/user/nuclei-templates",
        )
        assert "-t" in cmd
        idx = cmd.index("-t")
        val = cmd[idx + 1]
        assert "/home/user/nuclei-templates" in val
        assert "/repo/.nuclei" in val
        assert "," in val

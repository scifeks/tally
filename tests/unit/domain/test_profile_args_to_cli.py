"""Unit tests for profile_args_to_cli."""

from __future__ import annotations

from domain.tool_arg_profiles.cli import profile_args_to_cli
from domain.tool_arg_profiles.entry import (
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)


class TestProfileArgsToCli:
    def test_empty_args(self) -> None:
        result = profile_args_to_cli([])
        assert result == []

    def test_single_flag_arg(self) -> None:
        args = [ToolArgProfileFlagArg(name="--verbose")]
        result = profile_args_to_cli(args)
        assert result == ["--verbose"]

    def test_single_string_arg(self) -> None:
        args = [ToolArgProfileStringArg(name="--timeout", value="30")]
        result = profile_args_to_cli(args)
        assert result == ["--timeout", "30"]

    def test_single_file_arg(self) -> None:
        args = [ToolArgProfileFileArg(name="--config", path="/path/to/file")]
        result = profile_args_to_cli(args)
        assert result == ["--config", "/path/to/file"]

    def test_mixed_args_preserving_order(self) -> None:
        args = [
            ToolArgProfileFlagArg(name="--verbose"),
            ToolArgProfileStringArg(name="--timeout", value="30"),
            ToolArgProfileFileArg(name="--config", path="/etc/config.json"),
            ToolArgProfileFlagArg(name="--debug"),
        ]
        result = profile_args_to_cli(args)
        assert result == [
            "--verbose",
            "--timeout",
            "30",
            "--config",
            "/etc/config.json",
            "--debug",
        ]

    def test_file_arg_with_original_filename(self) -> None:
        args = [
            ToolArgProfileFileArg(
                name="--input",
                path="/tmp/uploaded_file.txt",
                original_filename="myfile.txt",
            )
        ]
        result = profile_args_to_cli(args)
        assert result == ["--input", "/tmp/uploaded_file.txt"]

    def test_multiple_string_args(self) -> None:
        args = [
            ToolArgProfileStringArg(name="--user", value="admin"),
            ToolArgProfileStringArg(name="--pass", value="secret"),
        ]
        result = profile_args_to_cli(args)
        assert result == ["--user", "admin", "--pass", "secret"]

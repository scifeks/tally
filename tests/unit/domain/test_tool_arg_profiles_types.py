"""Unit tests for domain.tool_arg_profiles.entry dataclasses."""

from __future__ import annotations

import pytest

from domain.tool_arg_profiles.entry import (
    ToolArgProfile,
    ToolArgProfileArg,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)


class TestToolArgProfileFlagArg:
    def test_constructs_with_default_type(self) -> None:
        arg = ToolArgProfileFlagArg(name="--verbose")
        assert arg.name == "--verbose"
        assert arg.type == "flag"

    def test_is_frozen(self) -> None:
        arg = ToolArgProfileFlagArg(name="--verbose")
        with pytest.raises(Exception):
            arg.name = "--quiet"  # type: ignore[misc]


class TestToolArgProfileStringArg:
    def test_carries_value(self) -> None:
        arg = ToolArgProfileStringArg(name="--config", value="rules.toml")
        assert arg.name == "--config"
        assert arg.value == "rules.toml"
        assert arg.type == "string"

    def test_operator_defaults_to_empty(self) -> None:
        arg = ToolArgProfileStringArg(name="--config", value="rules.toml")
        assert arg.operator == ""

    def test_operator_preserved(self) -> None:
        arg = ToolArgProfileStringArg(name="--redact", value="50", operator="=")
        assert arg.operator == "="

    def test_is_frozen(self) -> None:
        arg = ToolArgProfileStringArg(name="--config", value="rules.toml")
        with pytest.raises(Exception):
            arg.value = "other.toml"  # type: ignore[misc]


class TestToolArgProfileFileArg:
    def test_carries_path(self) -> None:
        arg = ToolArgProfileFileArg(name="--rules", path="arg_files/12/--rules.yml")
        assert arg.name == "--rules"
        assert arg.path == "arg_files/12/--rules.yml"
        assert arg.type == "file"

    def test_operator_defaults_to_empty(self) -> None:
        arg = ToolArgProfileFileArg(name="--rules", path="arg_files/1/--rules")
        assert arg.operator == ""

    def test_operator_preserved(self) -> None:
        arg = ToolArgProfileFileArg(
            name="--rules", path="arg_files/1/--rules", operator="="
        )
        assert arg.operator == "="

    def test_original_filename_defaults_to_none(self) -> None:
        arg = ToolArgProfileFileArg(name="--rules", path="arg_files/1/--rules")
        assert arg.original_filename is None

    def test_original_filename_preserved(self) -> None:
        arg = ToolArgProfileFileArg(
            name="--rules",
            path="arg_files/1/--rules",
            original_filename="custom_rules.yml",
        )
        assert arg.original_filename == "custom_rules.yml"

    def test_is_frozen(self) -> None:
        arg = ToolArgProfileFileArg(name="--rules", path="some/path.yml")
        with pytest.raises(Exception):
            arg.path = "other/path.yml"  # type: ignore[misc]


class TestToolArgProfile:
    def test_holds_mixed_arg_variants(self) -> None:
        args: list[ToolArgProfileArg] = [
            ToolArgProfileFlagArg(name="--verbose"),
            ToolArgProfileStringArg(name="--config", value="rules.toml"),
            ToolArgProfileFileArg(name="--rules", path="arg_files/12/--rules.yml"),
        ]
        profile = ToolArgProfile(
            id=12,
            tool_name="gitleaks",
            name="verbose-scan",
            args=args,
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        assert profile.id == 12
        assert profile.tool_name == "gitleaks"
        assert profile.name == "verbose-scan"
        assert len(profile.args) == 3
        assert profile.args[0].type == "flag"
        assert profile.args[1].type == "string"
        assert profile.args[2].type == "file"

    def test_is_frozen(self) -> None:
        profile = ToolArgProfile(
            id=1,
            tool_name="gitleaks",
            name="verbose-scan",
            args=[],
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        with pytest.raises(Exception):
            profile.name = "other"  # type: ignore[misc]

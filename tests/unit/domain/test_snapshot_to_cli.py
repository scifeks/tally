"""Unit tests for snapshot_to_cli."""

from __future__ import annotations

import pytest

from domain.tool_arg_profiles.cli import snapshot_to_cli


class TestSnapshotToCli:
    def test_empty_json_array(self) -> None:
        result = snapshot_to_cli("[]")
        assert result == []

    def test_single_flag_arg(self) -> None:
        snapshot = '[{"type": "flag", "name": "--verbose"}]'
        result = snapshot_to_cli(snapshot)
        assert result == ["--verbose"]

    def test_single_string_arg(self) -> None:
        snapshot = '[{"type": "string", "name": "--timeout", "value": "30"}]'
        result = snapshot_to_cli(snapshot)
        assert result == ["--timeout", "30"]

    def test_single_file_arg(self) -> None:
        snapshot = '[{"type": "file", "name": "--config", "path": "/etc/app.json"}]'
        result = snapshot_to_cli(snapshot)
        assert result == ["--config", "/etc/app.json"]

    def test_mixed_args(self) -> None:
        snapshot = """[
            {"type": "flag", "name": "--verbose"},
            {"type": "string", "name": "--timeout", "value": "30"},
            {"type": "file", "name": "--config", "path": "/etc/config.json"}
        ]"""
        result = snapshot_to_cli(snapshot)
        assert result == [
            "--verbose",
            "--timeout",
            "30",
            "--config",
            "/etc/config.json",
        ]

    def test_file_arg_with_original_filename(self) -> None:
        snapshot = (
            '{"type": "file", "name": "--input", "path": "/tmp/file.txt", '
            '"original_filename": "user_file.txt"}'
        )
        result = snapshot_to_cli(f"[{snapshot}]")
        assert result == ["--input", "/tmp/file.txt"]

    def test_invalid_json_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            snapshot_to_cli("{invalid json}")

    def test_json_not_array(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON array"):
            snapshot_to_cli('{"type": "flag"}')

    def test_json_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON array"):
            snapshot_to_cli('""')

    def test_json_number(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON array"):
            snapshot_to_cli("42")

    def test_array_item_not_dict(self) -> None:
        with pytest.raises(ValueError, match="Expected dict in array"):
            snapshot_to_cli('["string_value"]')

    def test_missing_type_field(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: type"):
            snapshot_to_cli('[{"name": "--verbose"}]')

    def test_unknown_arg_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown arg type"):
            snapshot_to_cli('[{"type": "unknown", "name": "--x"}]')

    def test_flag_missing_name(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: name"):
            snapshot_to_cli('[{"type": "flag"}]')

    def test_string_missing_name(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: name"):
            snapshot_to_cli('[{"type": "string", "value": "30"}]')

    def test_string_missing_value(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: value"):
            snapshot_to_cli('[{"type": "string", "name": "--timeout"}]')

    def test_file_missing_name(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: name"):
            snapshot_to_cli('[{"type": "file", "path": "/etc/config.json"}]')

    def test_file_missing_path(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: path"):
            snapshot_to_cli('[{"type": "file", "name": "--config"}]')

    def test_string_arg_with_equals_operator(self) -> None:
        snapshot = (
            '[{"type": "string", "name": "--redact", "value": "50", "operator": "="}]'
        )
        result = snapshot_to_cli(snapshot)
        assert result == ["--redact=50"]

    def test_string_arg_without_operator_defaults_space(self) -> None:
        snapshot = '[{"type": "string", "name": "--timeout", "value": "30"}]'
        result = snapshot_to_cli(snapshot)
        assert result == ["--timeout", "30"]

    def test_file_arg_with_equals_operator(self) -> None:
        snapshot = (
            '[{"type": "file", "name": "--config",'
            ' "path": "/etc/app.json", "operator": "="}]'
        )
        result = snapshot_to_cli(snapshot)
        assert result == ["--config=/etc/app.json"]

    def test_complex_mixed_snapshot(self) -> None:
        snapshot = """[
            {"type": "flag", "name": "--debug"},
            {"type": "string", "name": "--user", "value": "admin"},
            {"type": "string", "name": "--pass", "value": "secret123"},
            {"type": "file", "name": "--key", "path": "/home/user/.ssh/id_rsa"},
            {"type": "flag", "name": "--recursive"}
        ]"""
        result = snapshot_to_cli(snapshot)
        assert result == [
            "--debug",
            "--user",
            "admin",
            "--pass",
            "secret123",
            "--key",
            "/home/user/.ssh/id_rsa",
            "--recursive",
        ]

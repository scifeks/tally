"""Unit tests for ConfigManager (core.config.manager)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.manager import ConfigManager
from core.config.schemas import CommandEntry


@pytest.fixture()
def base_path(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(json.dumps({}))
    return tmp_path


@pytest.fixture()
def manager(base_path: Path) -> ConfigManager:
    return ConfigManager(str(base_path))


class TestConfigManager:
    def test_load_commands_config_returns_none_when_missing(
        self, manager: ConfigManager
    ) -> None:
        assert manager.load_commands_config() is None

    def test_save_and_load_commands_config_round_trip(
        self, manager: ConfigManager
    ) -> None:
        manager.save_commands_config(
            {
                "gitleaks": CommandEntry(
                    type="repo", location="local", path="/usr/bin/gitleaks"
                )
            }
        )
        result = manager.load_commands_config()
        assert result is not None
        assert "gitleaks" in result
        assert result["gitleaks"].type == "repo"
        assert result["gitleaks"].path == "/usr/bin/gitleaks"

    def test_load_global_config_raises_file_not_found_when_missing(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            ConfigManager(str(tmp_path))

    def test_invalid_type_in_global_json_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "global.json").write_text(
            json.dumps({"enrichment_max_concurrency": "not-a-number"})
        )
        with pytest.raises(ValueError):
            ConfigManager(str(tmp_path))

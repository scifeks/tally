"""Integration tests for global settings config persistence."""

import json

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def global_config_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "global.json").write_text(json.dumps({"ffuf_wordlist_paths": []}))
    return tmp_path


class TestGlobalSettingsRoundTrip:
    def test_wordlist_paths_stripped_on_load(self, global_config_dir):
        from core.config.manager import ConfigManager

        cm = ConfigManager(base_path=str(global_config_dir))
        assert not hasattr(cm.global_config, "ffuf_wordlist_paths")

    def test_migration_strips_old_wordlist_path(self, global_config_dir):
        config_file = global_config_dir / "config" / "global.json"
        config_file.write_text(json.dumps({"ffuf_wordlist_path": "/old/single.txt"}))

        from core.config.manager import ConfigManager

        cm = ConfigManager(base_path=str(global_config_dir))
        assert not hasattr(cm.global_config, "ffuf_wordlist_path")

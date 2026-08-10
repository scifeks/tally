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
    def test_save_and_load_wordlist_paths(self, global_config_dir):
        from core.config.manager import ConfigManager

        cm = ConfigManager(base_path=str(global_config_dir))
        assert cm.global_config.ffuf_wordlist_paths == []

        with cm.locked_global_config():
            gc = cm.load_global_config()
            data = gc.model_dump()
            data["ffuf_wordlist_paths"] = [
                "/a.txt",
                "/b.txt",
            ]
            updated = type(gc)(**data)
            cm.save_global_config(updated)

        cm2 = ConfigManager(base_path=str(global_config_dir))
        assert cm2.global_config.ffuf_wordlist_paths == [
            "/a.txt",
            "/b.txt",
        ]

    def test_migration_from_old_single_path(self, global_config_dir):
        config_file = global_config_dir / "config" / "global.json"
        config_file.write_text(json.dumps({"ffuf_wordlist_path": "/old/single.txt"}))

        from core.config.manager import ConfigManager

        cm = ConfigManager(base_path=str(global_config_dir))
        assert cm.global_config.ffuf_wordlist_paths == ["/old/single.txt"]

    def test_saved_config_round_trips_through_json(self, global_config_dir):
        from core.config.manager import ConfigManager

        cm = ConfigManager(base_path=str(global_config_dir))
        with cm.locked_global_config():
            gc = cm.load_global_config()
            data = gc.model_dump()
            data["ffuf_wordlist_paths"] = [
                "/x.txt",
                "/y.txt",
            ]
            updated = type(gc)(**data)
            cm.save_global_config(updated)

        raw = json.loads((global_config_dir / "config" / "global.json").read_text())
        assert raw["ffuf_wordlist_paths"] == [
            "/x.txt",
            "/y.txt",
        ]
        assert "ffuf_wordlist_path" not in raw

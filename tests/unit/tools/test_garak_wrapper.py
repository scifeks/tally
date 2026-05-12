"""Unit tests for garak wrapper configuration and command building."""

import tempfile
from pathlib import Path

import yaml

from infrastructure.tools.wrappers.base.garak import (
    _DEFAULT_TIMEOUT,
    _build_run_config,
    _remap_deprecated_keys,
)
from infrastructure.tools.wrappers.local.garak import GarakLocalTool


class TestGarakBuildCommand:
    def test_skip_unknown_flag_present(self, tmp_path):
        config = tmp_path / "garak.yaml"
        config.write_text("plugins:\n  target_type: ollama\n")
        tool = GarakLocalTool()
        cmd = tool.build_command(config_path=str(config))
        assert "--skip_unknown" in cmd

    def test_config_flag_present(self, tmp_path):
        config = tmp_path / "garak.yaml"
        config.write_text("plugins:\n  target_type: ollama\n")
        tool = GarakLocalTool()
        cmd = tool.build_command(config_path=str(config))
        assert "--config" in cmd
        idx = cmd.index("--config")
        assert cmd[idx + 1] == str(config)


class TestRemapDeprecatedKeys:
    def test_remaps_model_type(self):
        cfg = {"plugins": {"model_type": "ollama"}}
        _remap_deprecated_keys(cfg)
        assert cfg["plugins"]["target_type"] == "ollama"
        assert "model_type" not in cfg["plugins"]

    def test_remaps_model_name(self):
        cfg = {"plugins": {"model_name": "dolphin-mistral:latest"}}
        _remap_deprecated_keys(cfg)
        assert cfg["plugins"]["target_name"] == "dolphin-mistral:latest"
        assert "model_name" not in cfg["plugins"]

    def test_leaves_current_keys_unchanged(self):
        cfg = {
            "plugins": {
                "target_type": "ollama",
                "target_name": "llama3",
            }
        }
        _remap_deprecated_keys(cfg)
        assert cfg["plugins"]["target_type"] == "ollama"
        assert cfg["plugins"]["target_name"] == "llama3"

    def test_no_plugins_section(self):
        cfg = {"system": {"verbose": 1}}
        _remap_deprecated_keys(cfg)
        assert "plugins" not in cfg


class TestBuildRunConfig:
    def test_deprecated_keys_remapped_in_output(self):
        with tempfile.TemporaryDirectory() as td:
            user_cfg = Path(td) / "user.yaml"
            user_cfg.write_text(
                "plugins:\n  model_type: ollama\n  model_name: test-model\n"
            )
            out_dir = Path(td) / "output"
            out_dir.mkdir()

            result = _build_run_config(user_cfg, out_dir, "test")

            with open(result, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            assert cfg["plugins"]["target_type"] == "ollama"
            assert cfg["plugins"]["target_name"] == "test-model"
            assert "model_type" not in cfg["plugins"]
            assert "model_name" not in cfg["plugins"]

    def test_reporting_fields_injected(self):
        with tempfile.TemporaryDirectory() as td:
            user_cfg = Path(td) / "user.yaml"
            user_cfg.write_text("plugins:\n  target_type: ollama\n")
            out_dir = Path(td) / "output"
            out_dir.mkdir()

            result = _build_run_config(user_cfg, out_dir, "pfx")

            with open(result, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            assert cfg["reporting"]["report_prefix"] == "pfx"
            assert cfg["reporting"]["report_dir"] == str(out_dir.resolve())


class TestGarakTimeout:
    def test_default_timeout(self):
        tool = GarakLocalTool()
        assert tool.timeout == _DEFAULT_TIMEOUT

    def test_custom_timeout_from_config(self, tmp_path):
        config = tmp_path / "config" / "garak" / "1" / "garak.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("tally:\n  timeout: 7200\nplugins:\n  target_type: ollama\n")

        tool = GarakLocalTool()
        tool._output_dir = tmp_path / "output"
        tool._output_dir.mkdir()

        with open(config, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        tool._timeout = user_cfg.get("tally", {}).get("timeout", _DEFAULT_TIMEOUT)

        assert tool.timeout == 7200

    def test_missing_tally_section_uses_default(self, tmp_path):
        config = tmp_path / "garak.yaml"
        config.write_text("plugins:\n  target_type: ollama\n")

        tool = GarakLocalTool()

        with open(config, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        tool._timeout = user_cfg.get("tally", {}).get("timeout", _DEFAULT_TIMEOUT)

        assert tool.timeout == _DEFAULT_TIMEOUT

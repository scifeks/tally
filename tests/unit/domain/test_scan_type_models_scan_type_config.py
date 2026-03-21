"""Unit tests for ScanTypeConfig dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

from domain.tools.scan_types.models import ScanTypeConfig


class TestScanTypeConfig:
    def _make(self, **overrides) -> ScanTypeConfig:
        defaults: dict = dict(
            project_name="proj",
            base_path="/tmp/proj",
            config_manager=MagicMock(),
            event_bus=MagicMock(),
            display=MagicMock(),
            run_id=42,
        )
        defaults.update(overrides)
        return ScanTypeConfig(**defaults)

    def test_field_access(self) -> None:
        cfg = self._make()
        assert cfg.project_name == "proj"
        assert cfg.base_path == "/tmp/proj"
        assert cfg.run_id == 42

    def test_auto_approve_defaults_to_false(self) -> None:
        cfg = self._make()
        assert cfg.auto_approve is False

    def test_auto_approve_can_be_set_true(self) -> None:
        cfg = self._make(auto_approve=True)
        assert cfg.auto_approve is True

    def test_run_id_can_be_none(self) -> None:
        cfg = self._make(run_id=None)
        assert cfg.run_id is None

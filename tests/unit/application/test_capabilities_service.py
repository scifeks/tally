"""Unit tests for CapabilitiesService."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from application.capabilities.service import CapabilitiesService


def _runtime_service(*, claude_installed: bool = False) -> MagicMock:
    svc = MagicMock()
    svc.is_installed.side_effect = lambda name: name == "claude" and claude_installed
    return svc


def _write_global_config(base_path: Path, payload: dict) -> None:
    cfg_dir = base_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "global.json").write_text(json.dumps(payload))


class TestChatEnabled:
    def test_true_when_provider_is_ollama(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"chat_llm_provider": "ollama"})
        svc = CapabilitiesService(str(tmp_path), _runtime_service())
        assert svc.compute().chat_enabled is True

    def test_false_when_provider_is_other(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"chat_llm_provider": "claude"})
        svc = CapabilitiesService(str(tmp_path), _runtime_service())
        assert svc.compute().chat_enabled is False

    def test_false_when_config_missing(self, tmp_path: Path) -> None:
        svc = CapabilitiesService(str(tmp_path), _runtime_service())
        assert svc.compute().chat_enabled is False


class TestTriageEnabled:
    def test_true_when_claude_backend_configured_and_runtime_present(
        self, tmp_path: Path
    ) -> None:
        _write_global_config(tmp_path, {"triage_agent_provider": "claude_code"})
        svc = CapabilitiesService(
            str(tmp_path), _runtime_service(claude_installed=True)
        )
        assert svc.compute().triage_enabled is True

    def test_false_when_claude_backend_configured_and_runtime_missing(
        self, tmp_path: Path
    ) -> None:
        _write_global_config(tmp_path, {"triage_agent_provider": "claude_code"})
        svc = CapabilitiesService(
            str(tmp_path), _runtime_service(claude_installed=False)
        )
        assert svc.compute().triage_enabled is False

    def test_false_when_triage_disabled_in_config(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"triage_agent_provider": ""})
        svc = CapabilitiesService(
            str(tmp_path), _runtime_service(claude_installed=True)
        )
        assert svc.compute().triage_enabled is False

    def test_false_when_open_code_selected_but_not_implemented(
        self, tmp_path: Path
    ) -> None:
        _write_global_config(tmp_path, {"triage_agent_provider": "open_code"})
        svc = CapabilitiesService(
            str(tmp_path), _runtime_service(claude_installed=True)
        )
        assert svc.compute().triage_enabled is False


class TestReportRetention:
    def test_report_retention_enabled_is_hardcoded_false(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"report_retention_count": 25})
        svc = CapabilitiesService(str(tmp_path), _runtime_service())
        assert svc.compute().report_retention_enabled is False

    def test_max_report_history_reflects_config(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"report_retention_count": 25})
        svc = CapabilitiesService(str(tmp_path), _runtime_service())
        assert svc.compute().max_report_history == 25

    def test_max_report_history_default_when_config_missing(
        self, tmp_path: Path
    ) -> None:
        svc = CapabilitiesService(str(tmp_path), _runtime_service())
        assert svc.compute().max_report_history == 10


class TestComputeShape:
    def test_returns_capabilities_dataclass(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {
                "chat_llm_provider": "ollama",
                "triage_agent_provider": "claude_code",
            },
        )
        svc = CapabilitiesService(
            str(tmp_path), _runtime_service(claude_installed=True)
        )
        caps = svc.compute()
        assert caps.chat_enabled is True
        assert caps.triage_enabled is True
        assert caps.report_retention_enabled is False
        assert caps.max_report_history == 10

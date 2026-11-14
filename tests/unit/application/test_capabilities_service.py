"""Unit tests for CapabilitiesService."""

from __future__ import annotations

import json
from pathlib import Path

from application.capabilities.service import CapabilitiesService
from application.triage.readiness import TriageReadiness


def _write_global_config(base_path: Path, payload: dict) -> None:
    cfg_dir = base_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "global.json").write_text(json.dumps(payload))


def _readiness(enabled: bool = True) -> TriageReadiness:
    return TriageReadiness(
        provider="claude_code" if enabled else "",
        backend_label="Claude Code" if enabled else None,
        enabled=enabled,
        reason=None if enabled else "disabled",
    )


class TestChatEnabled:
    def test_true_when_provider_is_ollama(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {
                "ollama": {"base_url": "http://localhost:11434", "model": "test"},
                "chat_inference": {"provider": "ollama"},
            },
        )
        svc = CapabilitiesService(str(tmp_path), triage_readiness=_readiness())
        assert svc.compute().chat_enabled is True

    def test_false_when_provider_is_other(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {})
        svc = CapabilitiesService(str(tmp_path), triage_readiness=_readiness())
        assert svc.compute().chat_enabled is False

    def test_false_when_config_missing(self, tmp_path: Path) -> None:
        svc = CapabilitiesService(str(tmp_path), triage_readiness=_readiness())
        assert svc.compute().chat_enabled is False


class TestTriageEnabled:
    def test_true_when_readiness_enabled(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {"triage_agent_provider": "claude_code"},
        )
        svc = CapabilitiesService(
            str(tmp_path), triage_readiness=_readiness(enabled=True)
        )
        assert svc.compute().triage_enabled is True

    def test_false_when_readiness_disabled(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {"triage_agent_provider": "claude_code"},
        )
        svc = CapabilitiesService(
            str(tmp_path),
            triage_readiness=_readiness(enabled=False),
        )
        assert svc.compute().triage_enabled is False

    def test_mirrors_readiness_for_opencode(self, tmp_path: Path) -> None:
        readiness = TriageReadiness(
            provider="open_code",
            backend_label="OpenCode",
            enabled=True,
            reason=None,
        )
        _write_global_config(
            tmp_path,
            {"triage_agent_provider": "open_code"},
        )
        svc = CapabilitiesService(str(tmp_path), triage_readiness=readiness)
        assert svc.compute().triage_enabled is True


class TestReportRetention:
    def test_report_retention_enabled_is_hardcoded_false(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"report_retention_count": 25})
        svc = CapabilitiesService(str(tmp_path), triage_readiness=_readiness())
        assert svc.compute().report_retention_enabled is False

    def test_max_report_history_reflects_config(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"report_retention_count": 25})
        svc = CapabilitiesService(str(tmp_path), triage_readiness=_readiness())
        assert svc.compute().max_report_history == 25

    def test_max_report_history_default_when_config_missing(
        self, tmp_path: Path
    ) -> None:
        svc = CapabilitiesService(str(tmp_path), triage_readiness=_readiness())
        assert svc.compute().max_report_history == 10


class TestComputeShape:
    def test_returns_capabilities_dataclass(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "test",
                },
                "chat_inference": {"provider": "ollama"},
                "triage_agent_provider": "claude_code",
            },
        )
        svc = CapabilitiesService(
            str(tmp_path), triage_readiness=_readiness(enabled=True)
        )
        caps = svc.compute()
        assert caps.chat_enabled is True
        assert caps.triage_enabled is True
        assert caps.report_retention_enabled is False
        assert caps.max_report_history == 10
        assert caps.triage_backend_label == "Claude Code"

    def test_backend_label_exposed(self, tmp_path: Path) -> None:
        readiness = TriageReadiness(
            provider="ollama",
            backend_label="OpenCode (Ollama)",
            enabled=True,
            reason=None,
        )
        _write_global_config(tmp_path, {})
        svc = CapabilitiesService(str(tmp_path), triage_readiness=readiness)
        caps = svc.compute()
        assert caps.triage_backend_label == "OpenCode (Ollama)"

    def test_backend_label_none_when_disabled(self, tmp_path: Path) -> None:
        readiness = TriageReadiness(
            provider="",
            backend_label=None,
            enabled=False,
            reason="disabled",
        )
        _write_global_config(tmp_path, {})
        svc = CapabilitiesService(str(tmp_path), triage_readiness=readiness)
        caps = svc.compute()
        assert caps.triage_backend_label is None

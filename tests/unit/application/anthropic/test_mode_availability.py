from unittest.mock import MagicMock

import pytest

from application.anthropic.mode_availability import (
    BackgroundModeAvailabilityService,
)
from infrastructure.anthropic.oauth_detection import OAuthDetection


def _fake_config(api_key: str = "") -> MagicMock:
    cfg = MagicMock()
    cfg.claude.api_key = api_key
    return cfg


def test_both_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    svc = BackgroundModeAvailabilityService(
        config=_fake_config(api_key="sk-ant-cfg"),
        detect_oauth=lambda: OAuthDetection(available=True, reason="found"),
    )
    r = svc.evaluate()
    assert r.oauth_available is True
    assert r.api_key_available is True
    assert r.interactive_available is True


def test_only_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    svc = BackgroundModeAvailabilityService(
        config=_fake_config(api_key=""),
        detect_oauth=lambda: OAuthDetection(available=True, reason="found"),
    )
    r = svc.evaluate()
    assert r.oauth_available is True
    assert r.api_key_available is False
    assert r.api_key_reason is not None


def test_only_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    svc = BackgroundModeAvailabilityService(
        config=_fake_config(),
        detect_oauth=lambda: OAuthDetection(available=False, reason="no session"),
    )
    r = svc.evaluate()
    assert r.oauth_available is False
    assert r.api_key_available is True


def test_neither_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    svc = BackgroundModeAvailabilityService(
        config=_fake_config(),
        detect_oauth=lambda: OAuthDetection(available=False, reason="no session"),
    )
    r = svc.evaluate()
    assert r.oauth_available is False
    assert r.api_key_available is False
    assert r.interactive_available is True  # always true

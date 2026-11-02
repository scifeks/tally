import subprocess

import pytest

from infrastructure.anthropic.oauth_detection import detect_oauth_session


def test_setup_token_env_makes_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test_token")
    result = detect_oauth_session()
    assert result.available is True
    assert "CLAUDE_CODE_OAUTH_TOKEN" in result.reason


def test_auth_status_exit_zero_makes_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    class StubResult:
        returncode = 0

    def stub_run(*args, **kwargs):
        return StubResult()

    monkeypatch.setattr(subprocess, "run", stub_run)
    result = detect_oauth_session()
    assert result.available is True


def test_auth_status_exit_nonzero_makes_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    class StubResult:
        returncode = 1

    def stub_run(*args, **kwargs):
        return StubResult()

    monkeypatch.setattr(subprocess, "run", stub_run)
    result = detect_oauth_session()
    assert result.available is False
    assert "not logged in" in result.reason or "login" in result.reason


def test_claude_binary_missing_makes_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    def stub_run(*args, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(subprocess, "run", stub_run)
    result = detect_oauth_session()
    assert result.available is False
    assert "claude binary" in result.reason


def test_auth_status_timeout_makes_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    def stub_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5.0)

    monkeypatch.setattr(subprocess, "run", stub_run)
    result = detect_oauth_session()
    assert result.available is False
    assert "timed out" in result.reason

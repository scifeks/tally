from typing import Any, cast

import pytest

from core.config.schemas.claude_config import ClaudeConfig


def test_default_billing_method_defaults_to_none() -> None:
    cfg = ClaudeConfig()
    assert cfg.default_billing_method is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("plan", "plan"),
        ("api", "api"),
        ("PLAN", "plan"),
        ("API", "api"),
    ],
)
def test_default_billing_method_case_insensitive(value: str, expected: str) -> None:
    cfg = ClaudeConfig(default_billing_method=cast(Any, value))
    assert cfg.default_billing_method == expected


def test_default_billing_method_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        ClaudeConfig(default_billing_method=cast(Any, "free"))


def test_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_DEFAULT_BILLING_METHOD", "api")
    cfg = ClaudeConfig()
    assert cfg.default_billing_method == "api"


def test_config_value_wins_over_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_DEFAULT_BILLING_METHOD", "api")
    cfg = ClaudeConfig(default_billing_method="plan")
    assert cfg.default_billing_method == "plan"

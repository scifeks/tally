from typing import Any, cast

import pytest

from infrastructure.anthropic.subprocess_env import build_child_env


def test_plan_strips_api_key() -> None:
    base = {"ANTHROPIC_API_KEY": "sk-ant-should-be-removed", "PATH": "/usr/bin"}
    env = build_child_env("plan", api_key_source=None, base_env=base)
    assert "ANTHROPIC_API_KEY" not in env
    assert env["PATH"] == "/usr/bin"


def test_api_sets_api_key() -> None:
    base = {"PATH": "/usr/bin"}
    env = build_child_env("api", api_key_source="sk-ant-chosen", base_env=base)
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-chosen"


def test_api_overrides_existing_key() -> None:
    base = {"ANTHROPIC_API_KEY": "sk-ant-old", "PATH": "/usr/bin"}
    env = build_child_env("api", api_key_source="sk-ant-new", base_env=base)
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-new"


def test_api_without_key_source_raises() -> None:
    with pytest.raises(ValueError):
        build_child_env("api", api_key_source="", base_env={})


def test_unknown_method_raises() -> None:
    with pytest.raises(ValueError):
        build_child_env(cast(Any, "free"), api_key_source=None, base_env={})

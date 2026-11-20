from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from application.setup.billing_setup import (
    GlobalConfigReadError,
    run_billing_setup,
    set_default_billing_method,
)

# -- Stubs ----------------------------------------------------------------


@dataclass
class _FakeAvailability:
    oauth_available: bool = True
    api_key_available: bool = True
    interactive_available: bool = True
    oauth_reason: str = ""
    api_key_reason: str = ""


class _FakeAvailabilityService:
    def __init__(self, availability: _FakeAvailability) -> None:
        self._availability = availability

    def evaluate(self) -> _FakeAvailability:
        return self._availability


def _seed_config(base: Path, data: dict) -> Path:
    cfg_path = base / "config" / "global.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(data, indent=2) + "\n")
    return cfg_path


def _read_config(base: Path) -> dict:
    return json.loads((base / "config" / "global.json").read_text())


# -- set_default_billing_method -------------------------------------------


def test_set_default_billing_method_writes_value_preserving_siblings(
    tmp_path: Path,
) -> None:
    _seed_config(
        tmp_path,
        {
            "claude": {"api_key": "sk-ant-xxx"},
            "ollama": {"model": "llama3"},
        },
    )
    set_default_billing_method(str(tmp_path), "plan")
    result = _read_config(tmp_path)
    assert result["claude"]["default_billing_method"] == "plan"
    assert result["claude"]["api_key"] == "sk-ant-xxx"
    assert result["ollama"] == {"model": "llama3"}


def test_set_default_billing_method_none_removes_key(tmp_path: Path) -> None:
    _seed_config(
        tmp_path,
        {"claude": {"default_billing_method": "plan", "api_key": "sk-ant-xxx"}},
    )
    set_default_billing_method(str(tmp_path), None)
    result = _read_config(tmp_path)
    assert "default_billing_method" not in result["claude"]
    assert result["claude"]["api_key"] == "sk-ant-xxx"


def test_set_default_billing_method_rejects_invalid_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="'plan' or 'api'"):
        set_default_billing_method(str(tmp_path), "blah")  # type: ignore[arg-type]


# -- run_billing_setup ----------------------------------------------------


def test_run_billing_setup_writes_plan(tmp_path: Path) -> None:
    svc = _FakeAvailabilityService(_FakeAvailability())
    outputs: list[str] = []

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=lambda _prompt: "1",
        output_fn=outputs.append,
    )

    result = _read_config(tmp_path)
    assert result["claude"]["default_billing_method"] == "plan"


def test_run_billing_setup_skip_writes_nothing(tmp_path: Path) -> None:
    original = {"claude": {"api_key": "sk-ant-xxx"}, "ollama": {"model": "llama3"}}
    cfg_path = _seed_config(tmp_path, original)
    before = cfg_path.read_text()

    svc = _FakeAvailabilityService(_FakeAvailability())

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=lambda _prompt: "s",
        output_fn=lambda _msg: None,
    )

    assert cfg_path.read_text() == before


def test_run_billing_setup_rejects_bad_then_accepts(tmp_path: Path) -> None:
    answers = iter(["bogus", "2"])
    svc = _FakeAvailabilityService(_FakeAvailability())
    outputs: list[str] = []

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=lambda _prompt: next(answers),
        output_fn=outputs.append,
    )

    result = _read_config(tmp_path)
    assert result["claude"]["default_billing_method"] == "api"
    assert any("Unrecognized" in line for line in outputs)


def test_run_billing_setup_handles_no_credentials(tmp_path: Path) -> None:
    svc = _FakeAvailabilityService(
        _FakeAvailability(oauth_available=False, api_key_available=False)
    )
    outputs: list[str] = []

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=lambda _prompt: "s",
        output_fn=outputs.append,
    )

    assert any("No Anthropic credentials detected" in line for line in outputs)
    assert any("Skipped" in line for line in outputs)


def test_set_default_billing_method_creates_file_when_missing(
    tmp_path: Path,
) -> None:
    set_default_billing_method(str(tmp_path), "api")
    result = _read_config(tmp_path)
    assert result == {"claude": {"default_billing_method": "api"}}


def test_set_default_billing_method_raises_on_invalid_json(
    tmp_path: Path,
) -> None:
    cfg_path = tmp_path / "config" / "global.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("{invalid")
    with pytest.raises(GlobalConfigReadError, match="invalid JSON"):
        set_default_billing_method(str(tmp_path), "plan")


def test_set_default_billing_method_raises_on_non_dict_top_level(
    tmp_path: Path,
) -> None:
    cfg_path = tmp_path / "config" / "global.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("[1, 2, 3]")
    with pytest.raises(GlobalConfigReadError, match="expected a JSON object"):
        set_default_billing_method(str(tmp_path), "plan")


def test_set_default_billing_method_raises_on_non_dict_claude_block(
    tmp_path: Path,
) -> None:
    _seed_config(tmp_path, {"claude": "oops"})
    with pytest.raises(
        GlobalConfigReadError, match="expected claude block to be a dict"
    ):
        set_default_billing_method(str(tmp_path), "plan")


def test_run_billing_setup_handles_invalid_json_without_writing(
    tmp_path: Path,
) -> None:
    cfg_path = tmp_path / "config" / "global.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("{invalid")
    before = cfg_path.read_bytes()

    svc = _FakeAvailabilityService(_FakeAvailability())
    outputs: list[str] = []

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=lambda _prompt: "s",
        output_fn=outputs.append,
    )

    assert cfg_path.read_bytes() == before
    assert any("Cannot read" in line for line in outputs)


def test_run_billing_setup_auto_clears_the_key(tmp_path: Path) -> None:
    _seed_config(tmp_path, {"claude": {"default_billing_method": "plan"}})

    svc = _FakeAvailabilityService(_FakeAvailability())
    outputs: list[str] = []

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=lambda _prompt: "3",
        output_fn=outputs.append,
    )

    result = _read_config(tmp_path)
    assert "default_billing_method" not in result.get("claude", {})


def test_run_billing_setup_handles_eof(tmp_path: Path) -> None:
    original = {"claude": {"api_key": "sk-ant-xxx"}}
    cfg_path = _seed_config(tmp_path, original)
    before = cfg_path.read_bytes()

    svc = _FakeAvailabilityService(_FakeAvailability())
    outputs: list[str] = []

    def raise_eof(_prompt: str) -> str:
        raise EOFError

    run_billing_setup(
        str(tmp_path),
        svc,  # type: ignore[arg-type]
        input_fn=raise_eof,
        output_fn=outputs.append,
    )

    assert cfg_path.read_bytes() == before
    assert any("No input available" in line for line in outputs)

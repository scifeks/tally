"""Tests for TriageModeError."""

from __future__ import annotations

from domain.triage.errors import TriageModeError


def test_triage_mode_error_is_runtime_error() -> None:
    err = TriageModeError("requires MCP mode")
    assert isinstance(err, RuntimeError)
    assert str(err) == "requires MCP mode"

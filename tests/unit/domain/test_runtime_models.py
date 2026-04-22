"""Unit tests for domain.runtime.models dataclasses."""

from __future__ import annotations

import pytest

from domain.runtime.models import RuntimeDependencyRequirement, RuntimeDependencyStatus


class TestRuntimeDependencyRequirement:
    def test_fields_accessible(self) -> None:
        req = RuntimeDependencyRequirement(
            name="claude",
            binary="claude",
            install_hint="hint",
            required_for=("triage",),
        )
        assert req.name == "claude"
        assert req.binary == "claude"
        assert req.install_hint == "hint"
        assert req.required_for == ("triage",)

    def test_frozen(self) -> None:
        req = RuntimeDependencyRequirement(
            name="claude",
            binary="claude",
            install_hint="hint",
            required_for=(),
        )
        with pytest.raises(Exception):
            req.name = "other"  # type: ignore[misc]


class TestRuntimeDependencyStatus:
    def test_installed_fields(self) -> None:
        status = RuntimeDependencyStatus(
            name="claude",
            installed=True,
            binary_path="/usr/bin/claude",
            version="1.2.3",
            install_hint="hint",
            required_for=("triage",),
            error=None,
        )
        assert status.installed is True
        assert status.version == "1.2.3"
        assert status.error is None

    def test_not_installed_fields(self) -> None:
        status = RuntimeDependencyStatus(
            name="claude",
            installed=False,
            binary_path=None,
            version=None,
            install_hint="hint",
            required_for=("triage",),
            error="claude not on PATH",
        )
        assert status.installed is False
        assert status.binary_path is None
        assert status.error == "claude not on PATH"

    def test_frozen(self) -> None:
        status = RuntimeDependencyStatus(
            name="claude",
            installed=False,
            binary_path=None,
            version=None,
            install_hint="hint",
            required_for=(),
            error=None,
        )
        with pytest.raises(Exception):
            status.installed = True  # type: ignore[misc]

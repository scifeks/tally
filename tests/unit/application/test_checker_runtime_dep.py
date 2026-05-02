"""Tests for DependencyChecker with runtime_service injection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.startup.checker import DependencyChecker
from domain.runtime.models import RuntimeDependencyStatus


def _status(installed: bool) -> RuntimeDependencyStatus:
    return RuntimeDependencyStatus(
        name="claude",
        installed=installed,
        binary_path="/usr/bin/claude" if installed else None,
        version="1.0.0" if installed else None,
        install_hint="hint",
        required_for=("triage",),
        error=None if installed else "claude not on PATH",
    )


def _runtime_service(installed: bool) -> MagicMock:
    svc = MagicMock()
    svc.statuses.return_value = [_status(installed)]
    return svc


class TestDependencyCheckerRuntimeDep:
    def _run(self, installed: bool) -> object:
        svc = _runtime_service(installed)
        checker = DependencyChecker(runtime_service=svc)
        with (
            patch.object(checker, "check_python_version") as mock_py,
            patch.object(checker, "check_python_packages", return_value=[]),
            patch.object(checker, "check_system_tools", return_value=[]),
        ):
            mock_py.return_value = MagicMock(
                required=True, installed=True, warning=None
            )
            return checker.run()

    def test_all_required_present_when_installed(self) -> None:
        result = self._run(installed=True)
        assert result.all_required_present is True  # type: ignore[union-attr]

    def test_not_all_required_when_missing(self) -> None:
        result = self._run(installed=False)
        assert result.all_required_present is False  # type: ignore[union-attr]

    def test_missing_required_contains_claude(self) -> None:
        result = self._run(installed=False)
        names = [c.name for c in result.missing_required]  # type: ignore[union-attr]
        assert "claude" in names

    def test_no_runtime_service_excludes_claude(self) -> None:
        checker = DependencyChecker(runtime_service=None)
        with (
            patch.object(checker, "check_python_version") as mock_py,
            patch.object(checker, "check_python_packages", return_value=[]),
            patch.object(checker, "check_system_tools", return_value=[]),
        ):
            mock_py.return_value = MagicMock(
                required=True, installed=True, warning=None
            )
            result = checker.run()
        names = [c.name for c in result.checks]
        assert "claude" not in names

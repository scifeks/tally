"""Unit tests for RuntimeDependencyService."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.runtime.dependency_service import RuntimeDependencyService
from domain.runtime.models import RuntimeDependencyStatus


def _status(name: str = "claude", installed: bool = True) -> RuntimeDependencyStatus:
    return RuntimeDependencyStatus(
        name=name,
        installed=installed,
        binary_path="/usr/bin/claude" if installed else None,
        version="1.0.0" if installed else None,
        install_hint="hint",
        required_for=("triage",),
        error=None if installed else "not on PATH",
    )


def _probe(name: str = "claude", installed: bool = True) -> MagicMock:
    p = MagicMock()
    p.probe.return_value = _status(name, installed)
    return p


class TestRuntimeDependencyServiceConstruction:
    def test_probes_on_construction(self) -> None:
        probe = _probe()
        RuntimeDependencyService([probe])
        probe.probe.assert_called_once()

    def test_statuses_returns_cached_list(self) -> None:
        probe = _probe()
        svc = RuntimeDependencyService([probe])
        assert svc.statuses() == [_status()]
        assert probe.probe.call_count == 1

    def test_statuses_returns_copy(self) -> None:
        svc = RuntimeDependencyService([_probe()])
        assert svc.statuses() is not svc.statuses()


class TestRuntimeDependencyServiceRefresh:
    def test_refresh_re_probes(self) -> None:
        probe = _probe()
        svc = RuntimeDependencyService([probe])
        svc.refresh()
        assert probe.probe.call_count == 2

    def test_refresh_updates_cache(self) -> None:
        probe = MagicMock()
        probe.probe.side_effect = [
            _status(installed=True),
            _status(installed=False),
        ]
        svc = RuntimeDependencyService([probe])
        assert svc.is_installed("claude") is True
        svc.refresh()
        assert svc.is_installed("claude") is False


class TestRuntimeDependencyServiceLookup:
    def test_get_known_name(self) -> None:
        svc = RuntimeDependencyService([_probe("claude", True)])
        result = svc.get("claude")
        assert result is not None
        assert result.name == "claude"

    def test_get_unknown_name_returns_none(self) -> None:
        svc = RuntimeDependencyService([_probe("claude", True)])
        assert svc.get("docker") is None

    def test_is_installed_true(self) -> None:
        svc = RuntimeDependencyService([_probe("claude", True)])
        assert svc.is_installed("claude") is True

    def test_is_installed_false_when_not_installed(self) -> None:
        svc = RuntimeDependencyService([_probe("claude", False)])
        assert svc.is_installed("claude") is False

    def test_is_installed_false_when_missing(self) -> None:
        svc = RuntimeDependencyService([_probe("claude", True)])
        assert svc.is_installed("docker") is False

    def test_multiple_probes(self) -> None:
        svc = RuntimeDependencyService(
            [_probe("claude", True), _probe("docker", False)]
        )
        assert svc.is_installed("claude") is True
        assert svc.is_installed("docker") is False
        assert len(svc.statuses()) == 2
